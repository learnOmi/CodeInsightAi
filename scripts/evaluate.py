#!/usr/bin/env python3
"""评估框架 CLI 入口

用法示例::

    # 运行全部评估（mock 模式，无 agent）
    python scripts/evaluate.py

    # 按分类筛选
    python scripts/evaluate.py --category DP,AD

    # 按语言筛选
    python scripts/evaluate.py --languages python,javascript

    # 自定义数据目录
    python scripts/evaluate.py --data-dir ./my-data

    # 输出格式
    python scripts/evaluate.py --format json --output report.json
    python scripts/evaluate.py --format console

    # 保存快照并检测回归
    python scripts/evaluate.py --save-snapshot

    # 指定 prompt 版本
    python scripts/evaluate.py --prompt-version 2.0.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend package is on the path so imports work from project root.
_project_root = Path(__file__).resolve().parent.parent
_backend_root = _project_root / "codeinsight-backend"
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from codeinsight.evaluation.engine import EvalConfig, EvalEngine, EvalReport, Regression  # noqa: E402
from codeinsight.evaluation.history import SnapshotStore  # noqa: E402
from codeinsight.evaluation.reporters.console_reporter import ConsoleReporter  # noqa: E402
from codeinsight.evaluation.reporters.history_reporter import HistoryReporter  # noqa: E402
from codeinsight.evaluation.reporters.json_reporter import JsonReporter  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluate",
        description="CodeInsight AI 评估框架 — 运行知识点提取质量评估",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="按分类筛选，逗号分隔（如 DP,AD）或多次使用",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default=None,
        help="按语言筛选，逗号分隔（如 python,javascript）或多次使用",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="评估数据目录（JSON 文件），默认使用内置注册表",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "console"],
        default="json",
        help="报告输出格式（默认: json）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="JSON 报告输出文件路径",
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        default=False,
        help="评估完成后保存快照到历史文件",
    )
    parser.add_argument(
        "--prompt-version",
        type=str,
        default="unknown",
        help="Prompt 版本号（用于快照标记）",
    )
    parser.add_argument(
        "--eval-version",
        type=str,
        default="1.0.0",
        help="评估框架版本号（默认: 1.0.0）",
    )
    parser.add_argument(
        "--snapshot-path",
        type=str,
        default=None,
        help="历史快照 JSONL 文件路径（默认: evaluation/history/snapshots.jsonl）",
    )
    parser.add_argument(
        "--threshold-f1-drop",
        type=float,
        default=0.05,
        help="回归检测阈值：F1 下降超过此值视为回归（默认: 0.05）",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="启用详细输出",
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_csv(value: str | None) -> list[str] | None:
    """将逗号分隔字符串解析为列表，None 返回 None。"""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


async def run_evaluation(
    config: EvalConfig,
) -> EvalReport:
    """构建引擎并运行评估（mock 模式）。"""
    reporters: list = []

    if config.report_format == "console":
        reporters.append(ConsoleReporter(verbose=config.verbose))
    else:
        reporters.append(JsonReporter(output_path=config.output))
        reporters.append(ConsoleReporter())  # 始终在控制台打印摘要

    engine = EvalEngine(config=config, reporters=reporters)
    return await engine.run(
        languages=config.languages,
        categories=config.categories,
        data_dir=config.data_dir,
    )


def print_summary(report: EvalReport) -> None:
    """在控制台打印评估摘要。"""
    s = report.summary
    print("")
    print("=" * 60)
    print("评估摘要")
    print("=" * 60)
    print(f"  时间: {s.timestamp}")
    print(f"  整体 F1: {s.overall_f1:.4f}")
    print(f"  分类数: {s.categories_evaluated}")
    print(f"  用例数: {s.total_test_cases}")
    print(f"  提取量: {s.total_extracted}")
    print(f"  耗时: {s.total_time_seconds:.2f}s")
    print("")

    if report.by_language:
        print("--- 按语言 ---")
        print(f"  {'语言':<12} {'F1':<8} {'Precision':<12} {'Recall':<10} {'用例':<6}")
        print(f"  {'-' * 12} {'-' * 8} {'-' * 12} {'-' * 10} {'-' * 6}")
        for lang, m in sorted(report.by_language.items()):
            print(f"  {lang:<12} {m.f1:<8.4f} {m.precision:<12.4f} {m.recall:<10.4f} {m.cases:<6}")
        print("")

    if report.by_category:
        print("--- 按分类 ---")
        print(f"  {'分类':<12} {'F1':<8} {'Precision':<12} {'Recall':<10} {'用例':<6}")
        print(f"  {'-' * 12} {'-' * 8} {'-' * 12} {'-' * 10} {'-' * 6}")
        for cat, m in sorted(report.by_category.items()):
            print(f"  {cat:<12} {m.f1:<8.4f} {m.precision:<12.4f} {m.recall:<10.4f} {m.cases:<6}")
        print("")

    if report.regressions:
        print("--- 回归检测 ---")
        for r in report.regressions:
            print(
                f"  [{r.severity.upper()}] {r.dimension}: "
                f"{r.previous_f1:.4f} -> {r.current_f1:.4f} "
                f"(下降 {r.drop:.4f})"
            )
        print("")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> int:
    """评估主流程，返回退出码。"""

    # 构建配置
    languages = parse_csv(args.languages) if args.languages else None
    categories = parse_csv(args.category) if args.category else None

    config = EvalConfig(
        languages=languages,
        categories=categories,
        report_format=args.format,
        threshold_f1_drop=args.threshold_f1_drop,
        data_dir=args.data_dir,
        output=args.output,
        verbose=args.verbose,
        prompt_version=args.prompt_version,
    )

    # 运行评估
    report = await run_evaluation(config)

    # 保存快照 + 回归检测
    if args.save_snapshot:
        snapshot_store = SnapshotStore(
            path=Path(args.snapshot_path) if args.snapshot_path else None,
        )

        # 通过 HistoryReporter 保存
        history_reporter = HistoryReporter(
            store=snapshot_store,
            eval_version=args.eval_version,
        )
        await history_reporter.report(report)

        # 加载已保存的快照并检测回归
        raw_regressions = snapshot_store.detect_regressions(
            threshold_f1_drop=args.threshold_f1_drop,
        )
        report.regressions = [
            Regression(
                dimension=r["dimension"],
                previous_f1=r["previous_f1"],
                current_f1=r["current_f1"],
                drop=r["drop"],
                severity=r["severity"],
            )
            for r in raw_regressions
        ]

    # 打印摘要
    print_summary(report)

    # 检查是否有 critical 回归
    has_critical = any(r.severity == "critical" for r in report.regressions)
    if has_critical:
        print("\n[!] 检测到严重回归！请检查最近的代码变更。")
        return 1

    return 0


def cli() -> int:
    """命令行入口点。"""
    parser = build_parser()
    parsed = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if parsed.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    exit_code = asyncio.run(main(parsed))
    return exit_code


if __name__ == "__main__":
    sys.exit(cli())
