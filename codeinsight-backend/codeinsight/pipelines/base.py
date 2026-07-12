"""
管道基类

定义统一的管道接口：validate → transform → persist
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.pipelines.validators import ValidationResult


@dataclass
class PipelineResult:
    """管道执行结果"""

    success: bool
    total_count: int
    inserted_count: int
    skipped_count: int
    errors: list[dict] = field(default_factory=list)
    elapsed_ms: float = 0.0


class BasePipeline(ABC):
    """
    管道基类

    定义统一的管道接口：validate → transform → persist。
    子类实现具体的 validate 和 persist 方法。
    """

    def __init__(
        self,
        db: AsyncSession,
        batch_size: int = 500,
    ) -> None:
        self.db = db
        self.batch_size = batch_size

    async def run(
        self,
        repo_uuid: UUID,
        data: list[dict],
    ) -> PipelineResult:
        """
        执行管道

        流程：
        1. validate()  数据校验
        2. transform() 数据转换（默认返回原数据）
        3. persist()   持久化

        Args:
            repo_uuid: 仓库 UUID
            data: 待入库数据列表

        Returns:
            PipelineResult
        """
        import time

        start = time.perf_counter()

        # Step 1: 校验
        valid_items, errors = await self.validate(data)

        # Step 2: 转换
        transformed = await self.transform(valid_items)

        # Step 3: 持久化
        result = await self.persist(repo_uuid, transformed)

        elapsed = (time.perf_counter() - start) * 1000

        return PipelineResult(
            success=result is not None and result.inserted_count >= 0,
            total_count=len(data),
            inserted_count=result.inserted_count if result else 0,
            skipped_count=len(data) - len(valid_items) + (result.skipped_count if result else 0),
            errors=errors,
            elapsed_ms=round(elapsed, 2),
        )

    async def validate(self, data: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        数据校验，返回 (有效数据, 错误列表)

        子类可覆盖以实现自定义校验逻辑。

        Args:
            data: 原始数据列表

        Returns:
            (valid_items, errors)
        """
        valid_items: list[dict] = []
        errors: list[dict] = []

        for i, item in enumerate(data):
            result = self._validate_item(item)
            if result.valid:
                valid_items.append(item)
            else:
                errors.append(
                    {
                        "index": i,
                        "errors": result.errors,
                    }
                )

        return valid_items, errors

    @abstractmethod
    def _validate_item(self, item: dict) -> ValidationResult:
        """
        校验单条数据，子类必须实现

        Args:
            item: 单条数据

        Returns:
            ValidationResult
        """
        raise NotImplementedError

    async def transform(self, data: list[dict]) -> list[dict]:
        """
        数据转换，子类可覆盖

        Args:
            data: 有效数据列表

        Returns:
            转换后的数据列表
        """
        return data

    @abstractmethod
    async def persist(self, repo_uuid: UUID, data: list[dict]) -> PipelineResult:
        """
        持久化，子类必须实现

        Args:
            repo_uuid: 仓库 UUID
            data: 待持久化数据列表

        Returns:
            PipelineResult
        """
        raise NotImplementedError
