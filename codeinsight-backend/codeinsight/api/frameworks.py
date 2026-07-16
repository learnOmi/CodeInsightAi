"""
框架检测查询路由

提供框架检测结果的查询接口。
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories import FrameworkPatternDAO
from codeinsight.schemas import FrameworkPattern

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_framework_pattern_dao() -> FrameworkPatternDAO:
    """获取 FrameworkPatternDAO 实例（依赖注入）"""
    return FrameworkPatternDAO()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
FrameworkDaoDep = Annotated[FrameworkPatternDAO, Depends(get_framework_pattern_dao)]


@router.get(
    "/repositories/{repository_id}/frameworks",
    response_model=list[FrameworkPattern],
)
async def list_frameworks(
    repository_id: UUID,
    db: DbSession,
    dao: FrameworkDaoDep,
    category: Annotated[
        str | None,
        Query(description="按类别过滤（frontend/backend/database/messaging 等）"),
    ] = None,
    min_confidence: Annotated[
        float | None,
        Query(ge=0.0, le=1.0, description="最低置信度阈值"),
    ] = None,
):
    """
    获取仓库检测到的框架列表

    支持按类别和置信度过滤。
    """
    frameworks = await dao.get_by_repository(db, repository_id)

    if category:
        frameworks = [f for f in frameworks if f.category == category]

    if min_confidence is not None:
        frameworks = [f for f in frameworks if f.confidence >= min_confidence]

    return frameworks


@router.get(
    "/repositories/{repository_id}/frameworks/count",
    response_model=dict,
)
async def count_frameworks(
    repository_id: UUID,
    db: DbSession,
    dao: FrameworkDaoDep,
):
    """
    获取仓库检测到的框架数量统计
    """
    count = await dao.count_by_repository(db, repository_id)
    return {"count": count}
