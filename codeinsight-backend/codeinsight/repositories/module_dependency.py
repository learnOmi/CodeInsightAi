"""
ModuleDependency 数据访问对象

提供模块依赖实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import ModuleDependencyModel


class ModuleDependencyDAO:
    """模块依赖数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> ModuleDependencyModel:
        """创建模块依赖"""
        dep = ModuleDependencyModel(**data)
        db.add(dep)
        await db.flush()
        await db.refresh(dep)
        return dep

    async def create_many(self, db: AsyncSession, deps_data: list[dict]) -> list[ModuleDependencyModel]:
        """批量创建模块依赖"""
        dep_objects = [ModuleDependencyModel(**data) for data in deps_data]
        db.add_all(dep_objects)
        await db.flush()
        for obj in dep_objects:
            await db.refresh(obj)
        return dep_objects

    async def get_by_id(self, db: AsyncSession, dep_id: UUID) -> ModuleDependencyModel | None:
        """根据 ID 获取模块依赖"""
        result = await db.execute(select(ModuleDependencyModel).where(ModuleDependencyModel.id == dep_id))
        return result.scalar_one_or_none()

    async def get_dependencies(self, db: AsyncSession, importer_file_id: UUID) -> list[ModuleDependencyModel]:
        """获取该文件依赖的所有模块"""
        result = await db.execute(
            select(ModuleDependencyModel)
            .where(ModuleDependencyModel.importer_file_id == importer_file_id)
            .order_by(ModuleDependencyModel.import_name)
        )
        return list(result.scalars().all())

    async def get_dependents(self, db: AsyncSession, imported_file_id: UUID) -> list[ModuleDependencyModel]:
        """获取依赖该文件的所有模块"""
        result = await db.execute(
            select(ModuleDependencyModel)
            .where(ModuleDependencyModel.imported_file_id == imported_file_id)
            .order_by(ModuleDependencyModel.import_name)
        )
        return list(result.scalars().all())

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[ModuleDependencyModel]:
        """获取指定仓库的所有模块依赖"""
        result = await db.execute(
            select(ModuleDependencyModel)
            .where(ModuleDependencyModel.repository_id == repository_id)
            .order_by(ModuleDependencyModel.import_name)
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """删除指定仓库的所有模块依赖"""
        result = await db.execute(
            delete(ModuleDependencyModel).where(ModuleDependencyModel.repository_id == repository_id)
        )
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0  # type: ignore[attr-defined]

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的模块依赖数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(ModuleDependencyModel.repository_id == repository_id))
        return result.scalar() or 0
