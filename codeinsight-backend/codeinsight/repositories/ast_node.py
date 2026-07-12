"""
AstNode 数据访问对象

提供 AST 节点实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import AstNodeModel


class AstNodeDAO:
    """AST 节点数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> AstNodeModel:
        """
        创建 AST 节点

        Args:
            db: 异步数据库会话
            data: 包含节点字段的字典

        Returns:
            创建的 AstNodeModel 实例
        """
        node = AstNodeModel(**data)
        db.add(node)
        await db.flush()
        await db.refresh(node)
        return node

    async def create_many(self, db: AsyncSession, nodes_data: list[dict]) -> list[AstNodeModel]:
        """
        批量创建 AST 节点

        Args:
            db: 异步数据库会话
            nodes_data: 节点数据列表

        Returns:
            创建的 AstNodeModel 列表
        """
        node_objects = [AstNodeModel(**data) for data in nodes_data]
        db.add_all(node_objects)
        await db.flush()
        for obj in node_objects:
            await db.refresh(obj)
        return node_objects

    async def get_by_id(self, db: AsyncSession, node_id: UUID) -> AstNodeModel | None:
        """
        根据 ID 获取节点

        Args:
            db: 异步数据库会话
            node_id: 节点 ID

        Returns:
            AstNodeModel 实例，不存在则返回 None
        """
        result = await db.execute(select(AstNodeModel).where(AstNodeModel.id == node_id))
        return result.scalar_one_or_none()

    async def get_by_file(self, db: AsyncSession, file_id: UUID) -> list[AstNodeModel]:
        """
        获取指定文件的所有 AST 节点

        Args:
            db: 异步数据库会话
            file_id: 文件 ID

        Returns:
            AstNodeModel 列表
        """
        result = await db.execute(
            select(AstNodeModel)
            .where(AstNodeModel.file_id == file_id)
            .order_by(AstNodeModel.start_line, AstNodeModel.start_column)
        )
        return list(result.scalars().all())

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[AstNodeModel]:
        """
        获取指定仓库的所有 AST 节点

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            AstNodeModel 列表
        """
        result = await db.execute(
            select(AstNodeModel).where(AstNodeModel.repository_id == repository_id).order_by(AstNodeModel.start_line)
        )
        return list(result.scalars().all())

    async def get_by_repository_and_types(
        self, db: AsyncSession, repository_id: UUID, node_types: set[str]
    ) -> list[AstNodeModel]:
        """
        获取指定仓库的指定类型 AST 节点

        用于避免全量加载所有 AST 节点，降低内存消耗。

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID
            node_types: 节点类型集合（如 {"call"}、{"function", "method", "constructor"}）

        Returns:
            AstNodeModel 列表
        """
        result = await db.execute(
            select(AstNodeModel)
            .where(AstNodeModel.repository_id == repository_id, AstNodeModel.node_type.in_(node_types))
            .order_by(AstNodeModel.start_line)
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """
        删除指定仓库的所有 AST 节点

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            删除的记录数
        """
        result = await db.execute(delete(AstNodeModel).where(AstNodeModel.repository_id == repository_id))
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0  # type: ignore[attr-defined]

    async def delete_by_file(self, db: AsyncSession, file_id: UUID) -> int:
        """
        删除指定文件的所有 AST 节点

        Args:
            db: 异步数据库会话
            file_id: 文件 ID

        Returns:
            删除的记录数
        """
        result = await db.execute(delete(AstNodeModel).where(AstNodeModel.file_id == file_id))
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0  # type: ignore[attr-defined]

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """
        统计指定仓库的 AST 节点数量

        Args:
            db: 异步数据库会话
            repository_id: 仓库 ID

        Returns:
            节点数量
        """
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(AstNodeModel.repository_id == repository_id))
        return result.scalar() or 0
