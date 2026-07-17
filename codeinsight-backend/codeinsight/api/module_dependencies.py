"""
模块依赖查询路由

提供模块间依赖关系的查询接口。
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
from codeinsight.models import ModuleDependencyModel
from codeinsight.repositories import ModuleDependencyDAO
from codeinsight.schemas import ModuleDependency

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_module_dependency_dao() -> ModuleDependencyDAO:
    """获取 ModuleDependencyDAO 实例"""
    return ModuleDependencyDAO()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
ModuleDepDaoDep = Annotated[ModuleDependencyDAO, Depends(get_module_dependency_dao)]


@router.get(
    "/repositories/{repository_id}/module-dependencies",
    response_model=list[ModuleDependency],
)
async def list_module_dependencies(
    repository_id: UUID,
    db: DbSession,
    dao: ModuleDepDaoDep,
):
    """
    获取仓库的所有模块依赖关系

    返回模块间的导入关系，用于绘制模块级依赖图。
    """
    return await dao.get_by_repository(db, repository_id)


@router.get(
    "/repositories/{repository_id}/module-dependencies/count",
    response_model=dict,
)
async def count_module_dependencies(
    repository_id: UUID,
    db: DbSession,
    dao: ModuleDepDaoDep,
):
    """
    获取仓库的模块依赖数量统计
    """
    count = await dao.count_by_repository(db, repository_id)
    return {"count": count}


@router.get(
    "/repositories/{repository_id}/module-dependencies/stats",
    response_model=dict,
)
async def module_dependency_stats(
    repository_id: UUID,
    db: DbSession,
):
    """
    获取模块依赖分析统计信息

    包括：总依赖数、外部依赖数、内部依赖数、循环依赖数。
    """
    # 总依赖数
    total_result = await db.execute(select(func.count()).where(ModuleDependencyModel.repository_id == repository_id))
    total = total_result.scalar() or 0

    # 外部依赖（imported_file_id 为空表示外部库调用）
    external_result = await db.execute(
        select(func.count()).where(
            ModuleDependencyModel.repository_id == repository_id,
            ModuleDependencyModel.imported_file_id.is_(None),
        )
    )
    external = external_result.scalar() or 0

    # 内部依赖（imported_file_id 不为空）
    internal = total - external

    # 按 import_type 分组统计
    type_query = await db.execute(
        select(ModuleDependencyModel.import_type, func.count().label("cnt"))
        .where(ModuleDependencyModel.repository_id == repository_id)
        .group_by(ModuleDependencyModel.import_type)
    )
    by_type = {row[0]: row[1] for row in type_query}

    return {
        "total": total,
        "internal": internal,
        "external": external,
        "byType": by_type,
    }
