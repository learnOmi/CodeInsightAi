"""
评估数据注册表

定义评估数据集的元数据结构，支持按语言、分类、版本管理评估数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodeSnippet:
    """代码片段"""

    file: str
    language: str
    start_line: int
    end_line: int
    content: str
    highlighted_lines: list[int] = field(default_factory=list)
    is_synthetic: bool = False


@dataclass
class ExpectedPoint:
    """期望的知识点"""

    category: str
    prefix: str
    title: str
    description: str
    confidence: float = 1.0
    alternative_titles: list[str] = field(default_factory=list)
    code_lines_match: list[int] = field(default_factory=list)


@dataclass
class TestCase:
    """单个测试用例"""

    __test__ = False  # 防止 pytest 收集

    case_id: str
    description: str
    language: str
    category: str
    code_snippets: list[CodeSnippet]
    expected_points: list[ExpectedPoint]
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalDataset:
    """评估数据集元数据"""

    dataset_id: str
    language: str
    category: str
    prompt_version: str
    test_cases: list[TestCase]
    metadata: dict[str, Any] = field(default_factory=dict)


# 数据集注册表
_registry: dict[str, EvalDataset] = {}


def register_dataset(dataset: EvalDataset) -> None:
    """注册数据集

    Args:
        dataset: 评估数据集
    """
    _registry[dataset.dataset_id] = dataset


def get_dataset(dataset_id: str) -> EvalDataset | None:
    """获取数据集

    Args:
        dataset_id: 数据集 ID

    Returns:
        数据集，不存在时返回 None
    """
    return _registry.get(dataset_id)


def list_datasets(
    language: str | None = None,
    category: str | None = None,
) -> list[EvalDataset]:
    """列出数据集

    Args:
        language: 筛选语言
        category: 筛选分类

    Returns:
        数据集列表
    """
    results = []
    for dataset in _registry.values():
        if language and dataset.language != language:
            continue
        if category and dataset.category != category:
            continue
        results.append(dataset)
    return results


def load_dataset_from_file(filepath: str | Path) -> EvalDataset | None:
    """从文件加载数据集

    Args:
        filepath: JSON 文件路径

    Returns:
        数据集，加载失败时返回 None
    """
    import json

    filepath = Path(filepath)
    if not filepath.exists():
        return None

    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    test_cases: list[TestCase] = []
    for tc in data.get("test_cases", []):
        # 兼容旧格式（无 language 字段，从顶层获取）
        tc_language = tc.get("language", data.get("language", "unknown"))
        tc_category = tc.get("category", data.get("category", ""))

        code_snippets = [
            CodeSnippet(
                file=cs.get("file", ""),
                language=cs.get("language", tc_language),
                start_line=cs.get("start_line", 1),
                end_line=cs.get("end_line", 1),
                content=cs.get("content", ""),
                highlighted_lines=cs.get("highlighted_lines", []),
                is_synthetic=cs.get("is_synthetic", False),
            )
            for cs in tc.get("code_snippets", [])
        ]
        expected_points = [
            ExpectedPoint(
                category=ep.get("category", tc_category),
                prefix=ep.get("prefix", ""),
                title=ep.get("title", ""),
                description=ep.get("description", ""),
                confidence=ep.get("confidence", 1.0),
                alternative_titles=ep.get("alternative_titles", []),
                code_lines_match=ep.get("code_lines_match", []),
            )
            for ep in tc.get("expected_points", [])
        ]
        test_cases.append(
            TestCase(
                case_id=tc.get("id") or tc.get("case_id", f"case-{len(test_cases)}"),
                description=tc.get("description", ""),
                language=tc_language,
                category=tc_category,
                code_snippets=code_snippets,
                expected_points=expected_points,
                difficulty=tc.get("difficulty", "medium"),
                tags=tc.get("tags", []),
            )
        )

    dataset_id = (
        data.get("dataset_id")
        or data.get("repo_id")
        or f"{data.get('language', 'unknown')}-{data.get('category', 'unknown')}"
    )

    dataset = EvalDataset(
        dataset_id=dataset_id,
        language=data.get("language", "unknown"),
        category=data.get("category", "unknown"),
        prompt_version=data.get("prompt_version", "1.0.0"),
        test_cases=test_cases,
        metadata={
            "description": data.get("description", ""),
            "repo_id": data.get("repo_id", ""),
        },
    )
    register_dataset(dataset)
    return dataset


def load_datasets_from_dir(directory: str | Path) -> list[EvalDataset]:
    """从目录加载所有数据集

    Args:
        directory: 目录路径

    Returns:
        数据集列表
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []

    datasets = []
    for filepath in sorted(directory.rglob("*.json")):
        dataset = load_dataset_from_file(filepath)
        if dataset:
            datasets.append(dataset)
    return datasets
