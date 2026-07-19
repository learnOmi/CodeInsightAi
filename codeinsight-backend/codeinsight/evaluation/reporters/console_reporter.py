"""控制台报告输出器"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeinsight.evaluation.reporters.base import Reporter

if TYPE_CHECKING:
    from codeinsight.evaluation.engine import EvalReport

logger = logging.getLogger(__name__)


class ConsoleReporter(Reporter):
    """控制台报告输出器

    以人类可读的表格格式输出评估报告。
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    async def report(self, report: EvalReport) -> None:
        """输出控制台报告"""
        lines: list[str] = []
        s = report.summary

        lines.append("=" * 60)
        lines.append("评估报告")
        lines.append("=" * 60)
        lines.append(f"  时间: {s.timestamp}")
        lines.append(f"  整体 F1: {s.overall_f1:.4f}")
        lines.append(f"  分类数: {s.categories_evaluated}")
        lines.append(f"  用例数: {s.total_test_cases}")
        lines.append(f"  提取量: {s.total_extracted}")
        lines.append(f"  耗时: {s.total_time_seconds:.2f}s")
        lines.append("")

        # 按语言
        if report.by_language:
            lines.append("--- 按语言 ---")
            lines.append(f"  {'语言':<12} {'F1':<8} {'Precision':<12} {'Recall':<10} {'用例':<6}")
            lines.append(f"  {'-' * 12} {'-' * 8} {'-' * 12} {'-' * 10} {'-' * 6}")
            for lang, m in sorted(report.by_language.items()):
                lines.append(f"  {lang:<12} {m.f1:<8.4f} {m.precision:<12.4f} {m.recall:<10.4f} {m.cases:<6}")
            lines.append("")

        # 按分类
        if report.by_category:
            lines.append("--- 按分类 ---")
            lines.append(f"  {'分类':<12} {'F1':<8} {'Precision':<12} {'Recall':<10} {'用例':<6}")
            lines.append(f"  {'-' * 12} {'-' * 8} {'-' * 12} {'-' * 10} {'-' * 6}")
            for cat, m in sorted(report.by_category.items()):
                lines.append(f"  {cat:<12} {m.f1:<8.4f} {m.precision:<12.4f} {m.recall:<10.4f} {m.cases:<6}")
            lines.append("")

        # 按语言×分类
        if report.by_language_category and self.verbose:
            lines.append("--- 按语言×分类 ---")
            for lang, cats in sorted(report.by_language_category.items()):
                for cat, m in sorted(cats.items()):
                    lines.append(
                        f"  {lang}.{cat}: F1={m.f1:.4f} P={m.precision:.4f} R={m.recall:.4f} ({m.cases} cases)"
                    )
            lines.append("")

        # 回归检测
        if report.regressions:
            lines.append("--- 回归检测 ---")
            for r in report.regressions:
                lines.append(
                    f"  [{r.severity.upper()}] {r.dimension}: "
                    f"{r.previous_f1:.4f} → {r.current_f1:.4f} "
                    f"(下降 {r.drop:.4f})"
                )
            lines.append("")

        lines.append("=" * 60)

        print("\n".join(lines))
