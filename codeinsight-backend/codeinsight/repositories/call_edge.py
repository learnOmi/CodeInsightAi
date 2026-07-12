"""
CallEdge 数据访问对象

提供调用边实体的 CRUD 操作。
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import CallEdgeModel


class CallEdgeDAO:
    """调用边数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> CallEdgeModel:
        """创建调用边"""
        edge = CallEdgeModel(**data)
        db.add(edge)
        await db.flush()
        await db.refresh(edge)
        return edge

    async def create_many(self, db: AsyncSession, edges_data: list[dict]) -> list[CallEdgeModel]:
        """批量创建调用边"""
        edge_objects = [CallEdgeModel(**data) for data in edges_data]
        db.add_all(edge_objects)
        await db.flush()
        for obj in edge_objects:
            await db.refresh(obj)
        return edge_objects

    async def get_by_id(self, db: AsyncSession, edge_id: UUID) -> CallEdgeModel | None:
        """根据 ID 获取调用边"""
        result = await db.execute(select(CallEdgeModel).where(CallEdgeModel.id == edge_id))
        return result.scalar_one_or_none()

    async def get_callees(self, db: AsyncSession, caller_node_id: UUID) -> list[CallEdgeModel]:
        """获取该节点调用的所有目标（正向调用图）"""
        result = await db.execute(
            select(CallEdgeModel)
            .where(CallEdgeModel.caller_node_id == caller_node_id)
            .order_by(CallEdgeModel.start_line)
        )
        return list(result.scalars().all())

    async def get_callers(self, db: AsyncSession, callee_node_id: UUID) -> list[CallEdgeModel]:
        """获取调用该节点的所有调用者（反向调用图）"""
        result = await db.execute(
            select(CallEdgeModel)
            .where(CallEdgeModel.callee_node_id == callee_node_id)
            .order_by(CallEdgeModel.start_line)
        )
        return list(result.scalars().all())

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[CallEdgeModel]:
        """获取指定仓库的所有调用边"""
        result = await db.execute(
            select(CallEdgeModel).where(CallEdgeModel.repository_id == repository_id).order_by(CallEdgeModel.start_line)
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """删除指定仓库的所有调用边"""
        result = await db.execute(delete(CallEdgeModel).where(CallEdgeModel.repository_id == repository_id))
        await db.flush()
        return result.rowcount if hasattr(result, "rowcount") and result.rowcount else 0  # type: ignore[attr-defined]

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的调用边数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(CallEdgeModel.repository_id == repository_id))
        return result.scalar() or 0
