"""
ModuleDependency 数据访问对象

提供模块依赖实体的 CRUD 操作。
"""

from typing import cast
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
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
        # R-1 修复：UUID 由应用层生成，flush 后对象状态已完整，无需逐行 refresh
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
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def delete_by_file_ids(self, db: AsyncSession, repository_id: UUID, file_ids: list[UUID]) -> int:
        """
        删除与指定文件相关的模块依赖（增量分析用）

        删除条件：importer_file_id 或 imported_file_id 属于指定文件。

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            file_ids: 需要删除相关依赖的文件 ID 列表

        Returns:
            删除的记录数
        """
        if not file_ids:
            return 0

        # D-4 修复：合并为单次 DELETE，减少数据库往返
        result = await db.execute(
            delete(ModuleDependencyModel).where(
                and_(
                    ModuleDependencyModel.repository_id == repository_id,
                    or_(
                        ModuleDependencyModel.importer_file_id.in_(file_ids),
                        ModuleDependencyModel.imported_file_id.in_(file_ids),
                    ),
                )
            )
        )
        # M-5 修复：与 delete_by_repository 保持一致的 rowcount 读取方式
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的模块依赖数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(ModuleDependencyModel.repository_id == repository_id))
        return result.scalar() or 0
