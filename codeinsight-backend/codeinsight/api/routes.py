"""
API 路由查询路由

提供 API 路由信息的查询接口。
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories import ApiRouteDAO
from codeinsight.schemas import ApiRoute

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_api_route_dao() -> ApiRouteDAO:
    """获取 ApiRouteDAO 实例（依赖注入）"""
    return ApiRouteDAO()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
ApiRouteDaoDep = Annotated[ApiRouteDAO, Depends(get_api_route_dao)]


@router.get(
    "/repositories/{repository_id}/routes",
    response_model=list[ApiRoute],
)
async def list_routes(
    repository_id: UUID,
    db: DbSession,
    dao: ApiRouteDaoDep,
    http_method: Annotated[
        str | None,
        Query(description="按 HTTP 方法过滤（GET/POST/PUT/DELETE 等）"),
    ] = None,
    framework: Annotated[
        str | None,
        Query(description="按框架过滤（spring_boot/express/flask/fastapi 等）"),
    ] = None,
    path_pattern: Annotated[
        str | None,
        Query(description="路径模式模糊匹配"),
    ] = None,
):
    """
    获取仓库的 API 路由列表

    支持按 HTTP 方法、框架、路径模式过滤。
    """
    routes = await dao.get_by_repository(db, repository_id)

    if http_method:
        routes = [r for r in routes if r.http_method.upper() == http_method.upper()]

    if framework:
        routes = [r for r in routes if r.framework == framework]

    if path_pattern:
        routes = [r for r in routes if path_pattern.lower() in r.path_pattern.lower()]

    return routes


@router.get(
    "/repositories/{repository_id}/routes/count",
    response_model=dict,
)
async def count_routes(
    repository_id: UUID,
    db: DbSession,
    dao: ApiRouteDaoDep,
):
    """
    获取仓库的 API 路由数量统计
    """
    count = await dao.count_by_repository(db, repository_id)
    return {"count": count}
