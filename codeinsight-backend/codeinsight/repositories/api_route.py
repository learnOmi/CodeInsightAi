"""
ApiRoute 数据访问对象

提供 API 路由实体的 CRUD 操作。
"""

from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.models import ApiRouteModel


class ApiRouteDAO:
    """API 路由数据访问对象"""

    async def create(self, db: AsyncSession, data: dict) -> ApiRouteModel:
        """创建 API 路由"""
        route = ApiRouteModel(**data)
        db.add(route)
        await db.flush()
        await db.refresh(route)
        return route

    async def create_many(self, db: AsyncSession, routes_data: list[dict]) -> list[ApiRouteModel]:
        """批量创建 API 路由"""
        route_objects = [ApiRouteModel(**data) for data in routes_data]
        db.add_all(route_objects)
        await db.flush()
        # UUID 由应用层生成，flush 后对象状态已完整，无需逐行 refresh
        return route_objects

    async def get_by_id(self, db: AsyncSession, route_id: UUID) -> ApiRouteModel | None:
        """根据 ID 获取 API 路由"""
        result = await db.execute(select(ApiRouteModel).where(ApiRouteModel.id == route_id))
        return result.scalar_one_or_none()

    async def get_by_repository(self, db: AsyncSession, repository_id: UUID) -> list[ApiRouteModel]:
        """获取指定仓库的所有 API 路由"""
        result = await db.execute(
            select(ApiRouteModel)
            .where(ApiRouteModel.repository_id == repository_id)
            .order_by(ApiRouteModel.path_pattern)
        )
        return list(result.scalars().all())

    async def delete_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """删除指定仓库的所有 API 路由"""
        result = await db.execute(delete(ApiRouteModel).where(ApiRouteModel.repository_id == repository_id))
        await db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return cast(int, rowcount) or 0

    async def count_by_repository(self, db: AsyncSession, repository_id: UUID) -> int:
        """统计指定仓库的 API 路由数量"""
        from sqlalchemy import func

        result = await db.execute(select(func.count()).where(ApiRouteModel.repository_id == repository_id))
        return result.scalar() or 0
