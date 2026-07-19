"""评估历史快照管理

支持快照的保存、加载、回归检测。
快照存储在 JSONL 文件中，每行一个快照。
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HistorySnapshot:
    """历史快照（持久化格式）"""

    timestamp: str
    prompt_version: str
    eval_version: str = "1.0.0"
    metrics: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> HistorySnapshot:
        return HistorySnapshot(
            timestamp=data["timestamp"],
            prompt_version=data["prompt_version"],
            eval_version=data.get("eval_version", "1.0.0"),
            metrics=data.get("metrics", {}),
            summary=data.get("summary", {}),
        )


# 默认快照文件路径
_DEFAULT_SNAPSHOT_PATH = Path(__file__).parent / "history" / "snapshots.jsonl"


class SnapshotStore:
    """评估历史快照存储

    线程安全的 JSONL 文件读写，支持回归检测。
    """

    def __init__(self, path: Path | None = None):
        self._path = path or _DEFAULT_SNAPSHOT_PATH
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        report: Any,
        prompt_version: str,
        eval_version: str = "1.0.0",
    ) -> HistorySnapshot:
        """保存快照到 JSONL 文件

        Args:
            report: EvalReport 实例
            prompt_version: Prompt 版本号
            eval_version: 评估框架版本号

        Returns:
            保存的快照
        """
        metrics: dict[str, Any] = {
            "overall_f1": round(report.summary.overall_f1, 4),
            "total_extracted": report.summary.total_extracted,
            "total_test_cases": report.summary.total_test_cases,
        }

        # 收集各维度指标
        for label, dim in [("by_language", report.by_language), ("by_category", report.by_category)]:
            for key, m in dim.items():
                metrics[f"{label}.{key}.f1"] = round(m.f1, 4)

        snapshot = HistorySnapshot(
            timestamp=report.summary.timestamp,
            prompt_version=prompt_version,
            eval_version=eval_version,
            metrics=metrics,
            summary={
                "categories_evaluated": report.summary.categories_evaluated,
                "total_test_cases": report.summary.total_test_cases,
                "total_extracted": report.summary.total_extracted,
                "overall_f1": round(report.summary.overall_f1, 4),
                "total_time_seconds": report.summary.total_time_seconds,
            },
        )

        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot.to_dict(), ensure_ascii=False) + "\n")
            logger.info("快照已保存: %s (F1=%.4f)", snapshot.timestamp, snapshot.metrics["overall_f1"])

        return snapshot

    def load_snapshots(self) -> list[HistorySnapshot]:
        """加载所有历史快照

        Returns:
            快照列表（按时间排序）
        """
        with self._lock:
            if not self._path.exists():
                return []

            snapshots: list[HistorySnapshot] = []
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshots.append(HistorySnapshot.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning("跳过损坏的快照行: %s", exc)
            return snapshots

    def detect_regressions(
        self,
        threshold_f1_drop: float = 0.05,
    ) -> list[dict[str, Any]]:
        """检测回归：比较最新快照与上一个快照

        Args:
            threshold_f1_drop: F1 下降阈值

        Returns:
            回归列表
        """
        snapshots = self.load_snapshots()
        if len(snapshots) < 2:
            return []

        current = snapshots[-1]
        previous = snapshots[-2]

        regressions: list[dict[str, Any]] = []

        # 整体回归
        current_f1 = current.metrics.get("overall_f1", 0.0)
        previous_f1 = previous.metrics.get("overall_f1", 0.0)

        if previous_f1 > 0 and current_f1 < previous_f1:
            drop = previous_f1 - current_f1
            if drop >= threshold_f1_drop:
                regressions.append(
                    {
                        "dimension": "overall",
                        "previous_f1": round(previous_f1, 4),
                        "current_f1": round(current_f1, 4),
                        "drop": round(drop, 4),
                        "severity": "critical" if drop >= 0.1 else "warning",
                    }
                )

        # 各语言回归
        prev_lang_keys = {k for k in previous.metrics if k.startswith("by_language.")}
        cur_lang_keys = {k for k in current.metrics if k.startswith("by_language.")}
        common_lang_keys = sorted(prev_lang_keys & cur_lang_keys)
        for key in common_lang_keys:
            prev_val = previous.metrics[key]
            cur_val = current.metrics[key]
            if isinstance(prev_val, (int, float)) and isinstance(cur_val, (int, float)):
                drop = prev_val - cur_val
                if drop >= threshold_f1_drop:
                    lang = key.split(".", 1)[1]
                    regressions.append(
                        {
                            "dimension": f"language.{lang}",
                            "previous_f1": round(prev_val, 4),
                            "current_f1": round(cur_val, 4),
                            "drop": round(drop, 4),
                            "severity": "critical" if drop >= 0.1 else "warning",
                        }
                    )

        # 各分类回归
        prev_cat_keys = {k for k in previous.metrics if k.startswith("by_category.")}
        cur_cat_keys = {k for k in current.metrics if k.startswith("by_category.")}
        common_cat_keys = sorted(prev_cat_keys & cur_cat_keys)
        for key in common_cat_keys:
            prev_val = previous.metrics[key]
            cur_val = current.metrics[key]
            if isinstance(prev_val, (int, float)) and isinstance(cur_val, (int, float)):
                drop = prev_val - cur_val
                if drop >= threshold_f1_drop:
                    cat = key.split(".", 1)[1]
                    regressions.append(
                        {
                            "dimension": f"category.{cat}",
                            "previous_f1": round(prev_val, 4),
                            "current_f1": round(cur_val, 4),
                            "drop": round(drop, 4),
                            "severity": "critical" if drop >= 0.1 else "warning",
                        }
                    )

        return regressions

    def get_latest(self) -> HistorySnapshot | None:
        """获取最新快照

        Returns:
            最新快照，不存在时返回 None
        """
        snapshots = self.load_snapshots()
        return snapshots[-1] if snapshots else None
