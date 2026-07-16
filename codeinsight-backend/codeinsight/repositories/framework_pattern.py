"""
FrameworkPattern 数据访问对象

提供框架模式实体的 CRUD 操作。
"""

from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import FrameworkPatternModel


class FrameworkPatternDAO:
    """框架模式数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> FrameworkPatternModel:
        """创建框架模式"""
        pattern = FrameworkPatternModel(**data)
        db.add(pattern)
        await db.flush()
        await db.refresh(pattern)
        return pattern

    async def create_many(self, db: AsyncSession, patterns_data: list[dict]) -> list[FrameworkPatternModel]:
        """批量创建框架模式"""
        pattern_objects = [FrameworkPatternModel(**data) for data in patterns_data]
        db.add_all(pattern_objects)
        await db.flush()
        # UUID 由应用层生成，flush 后对象状态已完整，无需逐行 refresh
        return pattern_objects

    async def get_by_id(self, db: AsyncSession, pattern_id: UUID) -> FrameworkPatternModel | None:
        """根据 ID 获取框架模式"""
        result = await db.execute(select(FrameworkPatternModel).where(FrameworkPatternModel.id == pattern_id))
        return result.scalar_one_or_none()

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[FrameworkPatternModel]:
        """获取指定仓库的所有框架模式"""
        result = await db.execute(
            select(FrameworkPatternModel)
            .where(FrameworkPatternModel.repository_id == repository_id)
            .order_by(
                FrameworkPatternModel.framework,
                FrameworkPatternModel.confidence.desc(),
            )
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """删除指定仓库的所有框架模式"""
        result = await db.execute(
            delete(FrameworkPatternModel).where(FrameworkPatternModel.repository_id == repository_id)
        )
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def delete_by_repository_and_version(
        self, db: AsyncSession, repository_id: UUID, analysis_version_id: UUID
    ) -> int:
        """
        删除指定仓库和分析版本的所有框架模式

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            analysis_version_id: 分析版本 ID

        Returns:
            删除的记录数
        """
        result = await db.execute(
            delete(FrameworkPatternModel).where(
                FrameworkPatternModel.repository_id == repository_id,
                FrameworkPatternModel.analysis_version_id == analysis_version_id,
            )
        )
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的框架模式数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(FrameworkPatternModel.repository_id == repository_id))
        return result.scalar() or 0
