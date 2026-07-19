"""JSON 报告输出器"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from codeinsight.evaluation.reporters.base import Reporter

if TYPE_CHECKING:
    from codeinsight.evaluation.engine import EvalReport

logger = logging.getLogger(__name__)


class JsonReporter(Reporter):
    """JSON 报告输出器"""

    def __init__(self, output_path: str | None = None):
        self.output_path = output_path

    async def report(self, report: EvalReport) -> None:
        """输出 JSON 报告"""
        output = self._to_dict(report)

        if self.output_path:
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.info("评估报告已保存: %s", path)

        # 也输出到 stdout 的简短摘要
        logger.info(
            "评估完成: F1=%.4f, 分类=%d, 用例=%d, 耗时=%.2fs",
            report.summary.overall_f1,
            report.summary.categories_evaluated,
            report.summary.total_test_cases,
            report.summary.total_time_seconds,
        )

    def _to_dict(self, report: EvalReport) -> dict:
        """转换为字典"""
        return {
            "summary": {
                "categories_evaluated": report.summary.categories_evaluated,
                "total_test_cases": report.summary.total_test_cases,
                "total_extracted": report.summary.total_extracted,
                "overall_f1": round(report.summary.overall_f1, 4),
                "total_time_seconds": report.summary.total_time_seconds,
                "timestamp": report.summary.timestamp,
            },
            "by_language": {
                lang: {
                    "f1": round(m.f1, 4),
                    "precision": round(m.precision, 4),
                    "recall": round(m.recall, 4),
                    "extracted": m.extracted,
                    "expected": m.expected,
                    "cases": m.cases,
                    "avg_confidence": round(m.avg_confidence, 4),
                    "time_seconds": round(m.time_seconds, 2),
                }
                for lang, m in sorted(report.by_language.items())
            },
            "by_category": {
                cat: {
                    "f1": round(m.f1, 4),
                    "precision": round(m.precision, 4),
                    "recall": round(m.recall, 4),
                    "extracted": m.extracted,
                    "expected": m.expected,
                    "cases": m.cases,
                    "avg_confidence": round(m.avg_confidence, 4),
                    "time_seconds": round(m.time_seconds, 2),
                }
                for cat, m in sorted(report.by_category.items())
            },
            "by_language_category": {
                lang: {
                    cat: {
                        "f1": round(m.f1, 4),
                        "precision": round(m.precision, 4),
                        "recall": round(m.recall, 4),
                        "extracted": m.extracted,
                        "expected": m.expected,
                        "cases": m.cases,
                    }
                    for cat, m in sorted(cats.items())
                }
                for lang, cats in sorted(report.by_language_category.items())
            },
            "regressions": [
                {
                    "dimension": r.dimension,
                    "previous_f1": round(r.previous_f1, 4),
                    "current_f1": round(r.current_f1, 4),
                    "drop": round(r.drop, 4),
                    "severity": r.severity,
                }
                for r in (report.regressions or [])
            ],
        }
