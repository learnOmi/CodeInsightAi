"""
Prompt 格式验证测试

验证每个 prompt 文件的格式正确性：
- JSON 示例是否合法
- 占位符是否完整
- 输出格式是否与 Schema 一致
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROMPT_DIR = Path(__file__).parent.parent / "codeinsight" / "prompts"

# 每个 prompt 文件应包含的必选部分
REQUIRED_SECTIONS = {
    "base.md": ["角色定义", "输入格式", "输出格式", "约束"],
    "design_pattern.md": ["任务", "设计模式定义", "判断标准", "Few-shot 示例", "约束"],
    "architecture.md": ["任务", "架构决策类型", "判断标准", "Few-shot 示例", "约束"],
    "algorithm.md": ["任务", "算法类型", "判断标准", "Few-shot 示例", "约束"],
    "engineering.md": ["任务", "工程技巧类型", "判断标准", "Few-shot 示例", "约束"],
    "domain.md": ["任务", "领域知识类型", "判断标准", "Few-shot 示例", "约束"],
}

# 每个 prompt 文件应包含的必选字段说明
REQUIRED_OUTPUT_FIELDS = ["category", "prefix", "title", "description", "confidence", "code_snippets"]


def get_prompt_files():
    """获取所有 prompt 文件"""
    files = list(PROMPT_DIR.glob("*.md"))
    return [f for f in files if f.name != "__init__.py"]


class TestPromptStructure:
    """Prompt 结构完整性测试"""

    @pytest.mark.parametrize("fname", [f.name for f in get_prompt_files()])
    def test_prompt_file_exists(self, fname):
        """所有 prompt 文件存在"""
        filepath = PROMPT_DIR / fname
        assert filepath.exists(), f"Prompt 文件不存在: {filepath}"

    @pytest.mark.parametrize("fname, sections", REQUIRED_SECTIONS.items())
    def test_required_sections(self, fname, sections):
        """包含所有必选部分"""
        content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
        for section in sections:
            assert section in content, f"{fname} 缺少必选部分: {section}"

    @pytest.mark.parametrize("fname", [f.name for f in get_prompt_files()])
    def test_has_output_format_json(self, fname):
        """输出格式包含 JSON 示例"""
        content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
        assert "json" in content.lower(), f"{fname} 缺少 JSON 输出格式示例"


class TestPromptJsonValidity:
    """Prompt JSON 示例合法性测试"""

    @pytest.mark.parametrize("fname", [f.name for f in get_prompt_files()])
    def test_json_block_parsable(self, fname):
        """JSON 代码块可解析"""
        content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
        json_blocks = extract_json_blocks(content)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                assert isinstance(parsed, (list, dict)), f"JSON 应为对象或数组: {fname}"
            except json.JSONDecodeError as e:
                pytest.fail(f"{fname} 中的 JSON 示例无法解析: {e}")

    @pytest.mark.parametrize("fname", [f.name for f in get_prompt_files()])
    def test_json_example_has_required_fields(self, fname):
        """JSON 示例包含所有必选字段"""
        if fname == "base.md":
            pytest.skip("base.md 是模板，不包含完整示例")
        content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
        json_blocks = extract_json_blocks(content)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if any(k in item.get("title", "") for k in ["示例", "输出格式"]):
                        continue
                    for field in REQUIRED_OUTPUT_FIELDS:
                        assert field in item, f"{fname} JSON 示例缺少字段: {field}"
            except json.JSONDecodeError:
                pass

    @pytest.mark.parametrize("fname", [f.name for f in get_prompt_files()])
    def test_no_placeholder_left_unfilled(self, fname):
        """没有未替换的占位符（如 {{...}}）"""
        content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
        # 排除代码块中的内容
        code_blocks = extract_code_blocks(content)
        for block in code_blocks:
            # 检查是否有未替换的模板占位符
            placeholders = re.findall(r"\{\{.*?\}\}", block)
            if placeholders:
                pytest.fail(f"{fname} 中存在未替换的占位符: {placeholders}")


class TestPromptCrossReference:
    """Prompt 交叉引用测试"""

    def test_base_prompt_referenced_by_all(self):
        """所有分类 prompt 引用 base.md"""
        for fname in ["design_pattern.md", "architecture.md", "algorithm.md", "engineering.md", "domain.md"]:
            content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
            assert "base.md" in content or "通用约束" in content, f"{fname} 未引用 base.md"

    def test_consistent_category_values(self):
        """分类前缀与 base.md 一致"""
        base_content = (PROMPT_DIR / "base.md").read_text(encoding="utf-8")
        categories = re.findall(r"`(DP|AD|AL|ET|DK)`", base_content)
        assert len(categories) >= 5  # 5 个分类

        # 验证每个分类 prompt 的 category 值与 base.md 一致
        cat_map = {
            "design_pattern.md": "DP",
            "architecture.md": "AD",
            "algorithm.md": "AL",
            "engineering.md": "ET",
            "domain.md": "DK",
        }
        for fname, expected_cat in cat_map.items():
            content = (PROMPT_DIR / fname).read_text(encoding="utf-8")
            json_blocks = extract_json_blocks(content)
            for block in json_blocks:
                try:
                    parsed = json.loads(block)
                    items = parsed if isinstance(parsed, list) else [parsed]
                    for item in items:
                        if "category" in item and item["category"] != expected_cat:
                            pytest.fail(f"{fname} 包含非 {expected_cat} 分类的示例: {item['category']}")
                except json.JSONDecodeError:
                    pass


# ---- 辅助函数 ----


def extract_json_blocks(content: str) -> list[str]:
    """提取 markdown 中的 json 代码块，并清理占位符"""
    blocks = []
    pattern = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
    for match in pattern.finditer(content):
        block = match.group(1).strip()
        # 替换 ... 占位符为合法 JSON 值
        block = re.sub(r":\s*\.\.\.\s*$", ': ""', block, flags=re.MULTILINE)
        block = re.sub(r":\s*\.\.\.\s*,", ': "",', block, flags=re.MULTILINE)
        block = re.sub(r"\[\s*\.\.\.\s*\]", "[]", block)
        block = re.sub(r'"\s*\.\.\.\s*"', '""', block)
        blocks.append(block)
    return blocks


def extract_code_blocks(content: str) -> list[str]:
    """提取 markdown 中的所有代码块"""
    blocks = []
    pattern = re.compile(r"```.*?\n(.*?)\n```", re.DOTALL)
    for match in pattern.finditer(content):
        blocks.append(match.group(1).strip())
    return blocks
