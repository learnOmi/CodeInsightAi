"""
成本追踪器

记录 LLM 调用的 Token 消耗和成本，用于成本监控和优化。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
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
        self._records: deque[CostRecord] = deque()  # L-D5: 使用 deque 替代 list，pop(0) 为 O(1)
        self._max_records = max_records
        self._lock = asyncio.Lock()  # L-D6: 添加并发锁保护

    async def record(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        task_type: str = "",
    ) -> None:
        """
        记录一次 LLM 调用成本（异步并发安全）

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

        async with self._lock:
            self._records.append(record)

            if len(self._records) > self._max_records:
                self._records.popleft()  # L-D5: deque.popleft() 为 O(1)

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


class CostBudget:
    """
    LLM 调用预算控制器

    控制单次分析任务的最大预算，防止 API 费用超支。
    """

    def __init__(self, max_budget_usd: float = 10.0):
        """
        初始化预算控制器

        Args:
            max_budget_usd: 最大预算（USD），默认 10 美元
        """
        self._max_budget = max_budget_usd
        self._spent = 0.0
        self._lock = asyncio.Lock()

    @property
    def max_budget(self) -> float:
        """获取最大预算（USD）"""
        return self._max_budget

    @property
    def spent(self) -> float:
        """获取已花费金额（USD）"""
        return self._spent

    @property
    def remaining(self) -> float:
        """获取剩余预算（USD）"""
        return max(0.0, self._max_budget - self._spent)

    async def check(self, estimated_cost: float = 0.0) -> bool:
        """
        检查是否超出预算

        Args:
            estimated_cost: 预估的本次调用成本（USD），默认 0

        Returns:
            True 预算充足，False 已超出预算
        """
        async with self._lock:
            if self._spent + estimated_cost > self._max_budget:
                logger.warning(
                    "LLM 预算即将耗尽: spent=%.4f, estimated=%.4f, max=%.4f",
                    self._spent,
                    estimated_cost,
                    self._max_budget,
                )
                return False
            return True

    async def record(self, cost: float) -> None:
        """
        记录实际花费

        Args:
            cost: 实际花费金额（USD）
        """
        async with self._lock:
            self._spent += cost

    def reset(self) -> None:
        """重置预算"""
        self._spent = 0.0
        logger.info("预算已重置: max=%.2f", self._max_budget)
