"""
ExternalDependency 数据访问对象

提供外部依赖实体的 CRUD 操作。
"""

from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import ExternalDependencyModel


class ExternalDependencyDAO:
    """外部依赖数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> ExternalDependencyModel:
        """创建外部依赖"""
        dep = ExternalDependencyModel(**data)
        db.add(dep)
        await db.flush()
        await db.refresh(dep)
        return dep

    async def create_many(self, db: AsyncSession, deps_data: list[dict]) -> list[ExternalDependencyModel]:
        """批量创建外部依赖"""
        dep_objects = [ExternalDependencyModel(**data) for data in deps_data]
        db.add_all(dep_objects)
        await db.flush()
        return dep_objects

    async def get_by_id(self, db: AsyncSession, dep_id: UUID) -> ExternalDependencyModel | None:
        """根据 ID 获取外部依赖"""
        result = await db.execute(select(ExternalDependencyModel).where(ExternalDependencyModel.id == dep_id))
        return result.scalar_one_or_none()

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[ExternalDependencyModel]:
        """获取指定仓库的所有外部依赖"""
        result = await db.execute(
            select(ExternalDependencyModel)
            .where(ExternalDependencyModel.repository_id == repository_id)
            .order_by(ExternalDependencyModel.ecosystem, ExternalDependencyModel.artifact_name)
        )
        return list(result.scalars().all())

    async def get_by_repository_and_ecosystem(
        self, db: AsyncSession, repository_id: UUID, ecosystem: str
    ) -> list[ExternalDependencyModel]:
        """获取指定仓库和生态系统的外部依赖"""
        result = await db.execute(
            select(ExternalDependencyModel)
            .where(
                ExternalDependencyModel.repository_id == repository_id,
                ExternalDependencyModel.ecosystem == ecosystem,
            )
            .order_by(ExternalDependencyModel.artifact_name)
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """删除指定仓库的所有外部依赖"""
        result = await db.execute(
            delete(ExternalDependencyModel).where(ExternalDependencyModel.repository_id == repository_id)
        )
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的外部依赖数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(ExternalDependencyModel.repository_id == repository_id))
        return result.scalar() or 0
