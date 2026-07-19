#!/usr/bin/env python3
"""评估框架快速验证脚本（用于 pre-commit hook）

运行 Python 语言的评估（快速模式），验证评估框架未被破坏。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path
_project_root = Path(__file__).resolve().parent.parent
_backend_root = _project_root / "codeinsight-backend"
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from codeinsight.evaluation.engine import EvalConfig, EvalEngine  # noqa: E402
from codeinsight.evaluation.reporters.console_reporter import ConsoleReporter  # noqa: E402


async def main() -> int:
    config = EvalConfig(
        languages=["python"],
        report_format="console",
        threshold_f1=0.0,
    )
    engine = EvalEngine(config=config, reporters=[ConsoleReporter()])
    report = await engine.run(languages=["python"])

    # 检查是否有回归
    if report.regressions:
        for r in report.regressions:
            print(f"  [{r.severity.upper()}] {r.dimension}: {r.previous_f1:.4f} -> {r.current_f1:.4f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))