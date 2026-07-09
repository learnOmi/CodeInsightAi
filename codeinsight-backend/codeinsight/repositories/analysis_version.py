"""
AnalysisVersion 数据访问对象

提供分析版本实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import AnalysisVersionModel


class AnalysisVersionDAO:
    """分析版本数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> AnalysisVersionModel:
        """
        创建分析版本

        Args:
            db: 异步数据库会话
            data: 包含版本字段的字典

        Returns:
            创建的 AnalysisVersionModel 实例
        """
        version = AnalysisVersionModel(**data)
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version

    async def get_by_id(self, db: AsyncSession, version_id: UUID) -> AnalysisVersionModel | None:
        """
        根据 ID 获取分析版本

        Args:
            db: 异步数据库会话
            version_id: 版本 ID

        Returns:
            AnalysisVersionModel 实例，不存在则返回 None
        """
        result = await db.execute(
            select(AnalysisVersionModel).where(AnalysisVersionModel.id == version_id)
        )
        return result.scalar_one_or_none()

    async def list_by_repository(
        self,
        db: AsyncSession,
        repository_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AnalysisVersionModel]:
        """
        分页获取指定仓库的分析版本列表

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            skip: 跳过的记录数
            limit: 返回的记录数上限

        Returns:
            AnalysisVersionModel 列表（按 created_at 降序）
        """
        result = await db.execute(
            select(AnalysisVersionModel)
            .where(AnalysisVersionModel.repository_id == repository_id)
            .offset(skip)
            .limit(limit)
            .order_by(AnalysisVersionModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_version_tag(
        self,
        db: AsyncSession,
        repository_id: UUID,
        version_tag: str,
    ) -> AnalysisVersionModel | None:
        """
        根据版本号标签获取分析版本

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            version_tag: 版本号标签（如 v20260707-a3f2b1c）

        Returns:
            AnalysisVersionModel 实例，不存在则返回 None
        """
        result = await db.execute(
            select(AnalysisVersionModel)
            .where(
                AnalysisVersionModel.repository_id == repository_id,
                AnalysisVersionModel.version == version_tag,
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        db: AsyncSession,
        version_id: UUID,
        data: dict,
    ) -> AnalysisVersionModel:
        """
        更新分析版本

        Args:
            db: 异步数据库会话
            version_id: 版本 ID
            data: 要更新的字段字典

        Returns:
            更新后的 AnalysisVersionModel 实例

        Raises:
            ValueError: 版本不存在
        """
        version = await self.get_by_id(db, version_id)
        if version is None:
            raise ValueError(f"AnalysisVersion {version_id} not found")

        for key, value in data.items():
            setattr(version, key, value)

        await db.flush()
        await db.refresh(version)
        return version

    async def delete(self, db: AsyncSession, version_id: UUID) -> bool:
        """
        删除分析版本

        Args:
            db: 异步数据库会话
            version_id: 版本 ID

        Returns:
            是否删除成功
        """
        version = await self.get_by_id(db, version_id)
        if version is None:
            return False

        await db.delete(version)
        await db.flush()
        return True
