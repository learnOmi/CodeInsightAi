"""
成本追踪器

记录 LLM 调用的 Token 消耗和成本，用于成本监控和优化。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class CostRecord:
    """单次 LLM 调用的成本记录"""

    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    task_type: str = ""


class CostTracker:
    """
    LLM 成本追踪器

    记录每次 LLM 调用的 Token 使用量和成本，支持按时间段查询汇总。
    """

    def __init__(self, max_records: int = 10000):
        """
        初始化成本追踪器

        Args:
            max_records: 最大保留记录数
        """
        self._records: list[CostRecord] = []
        self._max_records = max_records

    def record(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        task_type: str = "",
    ) -> None:
        """
        记录一次 LLM 调用成本

        Args:
            model: 模型名称
            provider: 提供商名称
            prompt_tokens: 输入 Token 数
            completion_tokens: 输出 Token 数
            cost: 本次调用成本（USD）
            task_type: 任务类型
        """
        record = CostRecord(
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            task_type=task_type,
        )
        self._records.append(record)

        if len(self._records) > self._max_records:
            self._records.pop(0)

        logger.debug(
            "成本记录: model=%s, tokens=%d+%d, cost=$%.6f",
            model,
            prompt_tokens,
            completion_tokens,
            cost,
        )

    def get_daily_cost(self, days: int = 1) -> float:
        """
        获取指定天数内的总成本

        Args:
            days: 天数，默认 1 天

        Returns:
            总成本（USD）
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return sum(r.cost for r in self._records if r.timestamp >= cutoff)

    def get_cost_by_model(self, days: int = 7) -> dict[str, float]:
        """
        获取按模型分组的总成本

        Args:
            days: 天数，默认 7 天

        Returns:
            {model_name: cost_usd} 字典
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        costs: dict[str, float] = {}
        for r in self._records:
            if r.timestamp >= cutoff:
                costs[r.model] = costs.get(r.model, 0.0) + r.cost
        return costs

    def get_cost_by_task(self, days: int = 7) -> dict[str, float]:
        """
        获取按任务类型分组的总成本

        Args:
            days: 天数，默认 7 天

        Returns:
            {task_type: cost_usd} 字典
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        costs: dict[str, float] = {}
        for r in self._records:
            if r.timestamp >= cutoff and r.task_type:
                costs[r.task_type] = costs.get(r.task_type, 0.0) + r.cost
        return costs

    def get_total_stats(self) -> dict[str, float | int]:
        """
        获取总统计信息

        Returns:
            总记录数、总成本、总 Token 数等
        """
        total_cost = sum(r.cost for r in self._records)
        total_prompt = sum(r.prompt_tokens for r in self._records)
        total_completion = sum(r.completion_tokens for r in self._records)
        return {
            "total_records": len(self._records),
            "total_cost_usd": round(total_cost, 6),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        }

    def clear(self) -> None:
        """清空所有记录"""
        self._records.clear()
        logger.info("成本记录已清空")


# 全局单例
_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """获取全局成本追踪器单例"""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
