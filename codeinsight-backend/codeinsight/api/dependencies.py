"""
外部依赖查询路由

提供外部依赖的查询接口。
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories import ExternalDependencyDAO
from codeinsight.schemas import ExternalDependency

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_external_dependency_dao() -> ExternalDependencyDAO:
    """获取 ExternalDependencyDAO 实例（依赖注入）"""
    return ExternalDependencyDAO()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
ExtDepDaoDep = Annotated[ExternalDependencyDAO, Depends(get_external_dependency_dao)]


@router.get(
    "/repositories/{repository_id}/dependencies",
    response_model=list[ExternalDependency],
)
async def list_dependencies(
    repository_id: UUID,
    db: DbSession,
    dao: ExtDepDaoDep,
    ecosystem: Annotated[
        str | None,
        Query(description="按生态系统过滤（maven/npm/pip/go/cargo）"),
    ] = None,
    scope: Annotated[
        str | None,
        Query(description="按作用域过滤（compile/dev/test/runtime/peer）"),
    ] = None,
):
    """
    获取仓库的外部依赖列表

    支持按生态系统和作用域过滤。
    """
    if ecosystem:
        deps = await dao.get_by_repository_and_ecosystem(db, repository_id, ecosystem)
    else:
        deps = await dao.get_by_repository(db, repository_id)

    if scope:
        deps = [d for d in deps if d.scope == scope]

    return deps


@router.get(
    "/repositories/{repository_id}/dependencies/count",
    response_model=dict,
)
async def count_dependencies(
    repository_id: UUID,
    db: DbSession,
    dao: ExtDepDaoDep,
):
    """
    获取仓库的外部依赖数量统计
    """
    count = await dao.count_by_repository(db, repository_id)
    return {"count": count}
