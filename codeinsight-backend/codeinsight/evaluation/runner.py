"""
评估运行器

自动化评估脚本，加载 golden data → 调用 Agent → 计算指标 → 生成报告。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from codeinsight.evaluation.evaluator import KnowledgePointEvaluator
from codeinsight.evaluation.metrics import EvaluationResult

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

CATEGORY_DATA_FILES = {
    "DP": "design_pattern.json",
    "AD": "architecture.json",
    "AL": "algorithm.json",
    "ET": "engineering.json",
    "DK": "domain_knowledge.json",
}


def load_test_cases(category: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """加载测试用例

    Args:
        category: 分类筛选，为 None 则加载所有分类

    Returns:
        {category: [{test_case}, ...]}
    """
    cases: dict[str, list[dict[str, Any]]] = {}

    files_to_load = (
        [(cat, fname) for cat, fname in CATEGORY_DATA_FILES.items() if cat == category]
        if category
        else list(CATEGORY_DATA_FILES.items())
    )

    for cat, fname in files_to_load:
        filepath = DATA_DIR / fname
        if not filepath.exists():
            logger.warning("评估数据文件不存在: %s", filepath)
            continue

        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        cases[cat] = data.get("test_cases", [])
        logger.info("加载 %d 个 %s 测试用例", len(cases[cat]), cat)

    return cases


class EvaluationRunner:
    """评估运行器

    加载 golden data → 调用 Agent → 计算指标 → 生成报告。
    """

    def __init__(self, agent_fn=None):
        """初始化

        Args:
            agent_fn: Agent 函数，接收 (code_snippets, category) 返回提取的知识点列表。
                      为 None 时使用 mock 模式（返回 expected_points 模拟理想情况）。
        """
        self._agent_fn = agent_fn
        self._evaluator = KnowledgePointEvaluator()

    async def run(
        self,
        category: str | None = None,
        report_file: str | None = None,
    ) -> dict[str, Any]:
        """运行评估

        Args:
            category: 分类筛选
            report_file: 报告输出路径，为 None 则只返回字典

        Returns:
            评估汇总报告
        """
        test_cases = load_test_cases(category)
        all_results: list[EvaluationResult] = []
        total_start = time.time()

        for cat, cases in test_cases.items():
            logger.info("评估分类 %s: %d 个用例", cat, len(cases))
            case_results = []

            for case in cases:
                case_id = case.get("id", "unknown")
                code_snippets = case.get("code_snippets", [])
                expected_points = case.get("expected_points", [])

                # 提取知识点
                if self._agent_fn:
                    extracted = await self._agent_fn(code_snippets, cat)
                else:
                    # mock 模式：返回 expected_points，模拟理想 Agent
                    extracted = expected_points

                # 评估
                result = await self._evaluator.evaluate(
                    repo_id=case_id,
                    extracted_points=extracted,
                    expected_points=expected_points,
                )
                case_results.append(result)

            # 汇总分类结果
            merged = self._merge_case_results(cat, case_results)
            all_results.append(merged)

        # 整体汇总
        summary = self._build_summary(all_results, time.time() - total_start)

        if report_file:
            report_path = Path(report_file)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info("评估报告已保存: %s", report_path)

        return summary

    def _merge_case_results(
        self,
        category: str,
        results: list[EvaluationResult],
    ) -> EvaluationResult:
        """合并多个用例的结果"""
        if not results:
            return EvaluationResult(
                repo_id=category,
                overall_f1=0.0,
                overall_precision=0.0,
                overall_recall=0.0,
                category_metrics=[],
                total_extracted=0,
                total_expected=0,
                total_cases=0,
                avg_confidence=0.0,
                execution_time=0.0,
            )

        total_extracted = sum(r.total_extracted for r in results)
        total_expected = sum(r.total_expected for r in results)
        total_cases = len(results)
        avg_f1 = sum(r.overall_f1 for r in results) / total_cases
        avg_precision = sum(r.overall_precision for r in results) / total_cases
        avg_recall = sum(r.overall_recall for r in results) / total_cases
        avg_confidence = sum(r.avg_confidence for r in results) / total_cases
        total_time = sum(r.execution_time for r in results)

        return EvaluationResult(
            repo_id=category,
            overall_f1=avg_f1,
            overall_precision=avg_precision,
            overall_recall=avg_recall,
            category_metrics=[],
            total_extracted=total_extracted,
            total_expected=total_expected,
            total_cases=total_cases,
            avg_confidence=avg_confidence,
            execution_time=total_time,
        )

    def _build_summary(
        self,
        results: list[EvaluationResult],
        total_time: float,
    ) -> dict[str, Any]:
        """构建汇总报告"""
        category_summaries = {}
        total_extracted = 0
        total_cases = 0

        for r in results:
            cat = r.repo_id
            category_summaries[cat] = {
                "f1": round(r.overall_f1, 4),
                "precision": round(r.overall_precision, 4),
                "recall": round(r.overall_recall, 4),
                "extracted": r.total_extracted,
                "expected": r.total_expected,
                "cases": r.total_cases,
                "avg_confidence": round(r.avg_confidence, 4),
                "time_seconds": round(r.execution_time, 2),
            }
            total_extracted += r.total_extracted
            total_cases += r.total_cases

        overall_f1 = sum(r.overall_f1 for r in results) / len(results) if results else 0.0

        return {
            "summary": {
                "categories_evaluated": len(results),
                "total_test_cases": total_cases,
                "total_extracted": total_extracted,
                "overall_f1": round(overall_f1, 4),
                "total_time_seconds": round(total_time, 2),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            "category_results": category_summaries,
        }
