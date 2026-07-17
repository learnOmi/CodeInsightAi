"""
项目统计信息路由

提供仓库级别的全局统计概览，用于前端仪表盘展示。
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.models import (
    ApiRouteModel,
    AstNodeModel,
    CallEdgeModel,
    ExternalDependencyModel,
    FileModel,
    FrameworkPatternModel,
    ModuleDependencyModel,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/repositories/{repository_id}/stats", response_model=dict)
async def repository_stats(
    repository_id: UUID,
    db: DbSession,
):
    """
    获取仓库的全方位统计信息

    返回一个一站式统计概览，覆盖文件、AST 节点、调用边、模块依赖、
    外部依赖、框架、API 路由等维度的数量统计。
    """

    # 文件统计
    file_count = await db.execute(select(func.count()).where(FileModel.repository_id == repository_id))
    fc = file_count.scalar() or 0

    total_lines = await db.execute(
        select(func.coalesce(func.sum(FileModel.line_count), 0)).where(FileModel.repository_id == repository_id)
    )
    tl = total_lines.scalar() or 0

    # 语言分布
    lang_query = await db.execute(
        select(FileModel.language, func.count().label("cnt"))
        .where(FileModel.repository_id == repository_id)
        .group_by(FileModel.language)
        .order_by(func.count().desc())
    )
    language_distribution = {row[0]: row[1] for row in lang_query}

    # AST 节点统计
    node_count = await db.execute(select(func.count()).where(AstNodeModel.repository_id == repository_id))
    nc = node_count.scalar() or 0

    node_type_query = await db.execute(
        select(AstNodeModel.node_type, func.count().label("cnt"))
        .where(AstNodeModel.repository_id == repository_id)
        .group_by(AstNodeModel.node_type)
        .order_by(func.count().desc())
    )
    node_type_distribution = {row[0]: row[1] for row in node_type_query}

    # 调用边统计
    edge_count = await db.execute(select(func.count()).where(CallEdgeModel.repository_id == repository_id))
    ec = edge_count.scalar() or 0

    edge_type_query = await db.execute(
        select(CallEdgeModel.call_type, func.count().label("cnt"))
        .where(CallEdgeModel.repository_id == repository_id)
        .group_by(CallEdgeModel.call_type)
        .order_by(func.count().desc())
    )
    edge_type_distribution = {row[0]: row[1] for row in edge_type_query}

    # 模块依赖统计
    mod_dep_count = await db.execute(select(func.count()).where(ModuleDependencyModel.repository_id == repository_id))
    mdc = mod_dep_count.scalar() or 0

    # 外部依赖统计
    ext_dep_count = await db.execute(select(func.count()).where(ExternalDependencyModel.repository_id == repository_id))
    edc = ext_dep_count.scalar() or 0

    eco_query = await db.execute(
        select(ExternalDependencyModel.ecosystem, func.count().label("cnt"))
        .where(ExternalDependencyModel.repository_id == repository_id)
        .group_by(ExternalDependencyModel.ecosystem)
        .order_by(func.count().desc())
    )
    ecosystem_distribution = {row[0]: row[1] for row in eco_query}

    # 框架统计
    fw_count = await db.execute(select(func.count()).where(FrameworkPatternModel.repository_id == repository_id))
    fwc = fw_count.scalar() or 0

    # API 路由统计
    route_count = await db.execute(select(func.count()).where(ApiRouteModel.repository_id == repository_id))
    rc = route_count.scalar() or 0

    return {
        "fileCount": fc,
        "totalLines": tl,
        "languageDistribution": language_distribution,
        "nodeCount": nc,
        "nodeTypeDistribution": node_type_distribution,
        "edgeCount": ec,
        "edgeTypeDistribution": edge_type_distribution,
        "moduleDependencyCount": mdc,
        "externalDependencyCount": edc,
        "ecosystemDistribution": ecosystem_distribution,
        "frameworkCount": fwc,
        "routeCount": rc,
    }
