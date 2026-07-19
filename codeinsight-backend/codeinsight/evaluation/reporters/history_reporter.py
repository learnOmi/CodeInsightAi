"""历史快照报告输出器"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeinsight.evaluation.history import SnapshotStore
from codeinsight.evaluation.reporters.base import Reporter

if TYPE_CHECKING:
    from codeinsight.evaluation.engine import EvalReport

logger = logging.getLogger(__name__)


class HistoryReporter(Reporter):
    """历史快照报告输出器

    在评估完成后自动保存快照，用于后续回归检测。
    """

    def __init__(self, store: SnapshotStore | None = None, eval_version: str = "1.0.0"):
        self._store = store or SnapshotStore()
        self._eval_version = eval_version

    async def report(self, report: EvalReport) -> None:
        """保存评估快照"""
        prompt_version = "unknown"
        if hasattr(report, "config") and report.config is not None:
            prompt_version = getattr(report.config, "prompt_version", "unknown")

        self._store.save_snapshot(
            report=report,
            prompt_version=prompt_version,
            eval_version=self._eval_version,
        )
