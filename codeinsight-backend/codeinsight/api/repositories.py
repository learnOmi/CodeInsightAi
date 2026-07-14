"""
仓库管理路由

提供仓库的增删改查接口。
"""

import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.exceptions import RepositoryNotFoundError, RepositoryPathExistsError
from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import Repository, RepositoryCreate, RepositoryUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_repository_dao() -> RepositoryDAO:
    """获取 RepositoryDAO 实例（依赖注入）"""
    return RepositoryDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RepoDaoDep = Annotated[RepositoryDAO, Depends(get_repository_dao)]


@router.post("", response_model=Repository, status_code=201)
async def create_repository(
    request: RepositoryCreate,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    添加代码仓库

    添加一个新的代码仓库，如果 auto_analyze 为 True 则自动提交分析任务。
    """
    # 验证路径是否存在且为目录
    p = Path(request.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {request.path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录: {request.path}")

    # 检查路径是否已存在
    if await dao.exists_by_path(db, request.path):
        raise RepositoryPathExistsError(request.path)

    repo = await dao.create(db, request)

    # 创建后自动分析
    if request.auto_analyze:
        # 显式提交，确保分析任务（独立 session）能查到仓库记录
        await db.commit()
        from codeinsight.api.analysis import _trigger_analysis

        await _trigger_analysis(repo.id, repo)

    return repo


@router.get("", response_model=list[Repository])
async def list_repositories(
    db: DbSession,
    dao: RepoDaoDep,
    skip: Annotated[int, Query(ge=0, description="跳过的记录数")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="返回的记录数")] = 100,
):
    """
    获取仓库列表

    分页返回用户的所有仓库。
    """
    repos = await dao.list(db, skip=skip, limit=limit)
    return repos


@router.get("/{repository_id}", response_model=Repository)
async def get_repository(
    repository_id: UUID,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    获取仓库详情
    """
    repo = await dao.get_by_id(db, repository_id)

    if repo is None:
        raise RepositoryNotFoundError(str(repository_id))

    return repo


@router.put("/{repository_id}", response_model=Repository)
async def update_repository(
    repository_id: UUID,
    request: RepositoryUpdate,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    更新仓库信息
    """
    # 检查仓库是否存在
    existing = await dao.get_by_id(db, repository_id)
    if existing is None:
        raise RepositoryNotFoundError(str(repository_id))

    repo = await dao.update(db, repository_id, request)
    return repo


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: UUID,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    删除仓库及其所有分析数据
    """
    deleted = await dao.delete(db, repository_id)
    if not deleted:
        raise RepositoryNotFoundError(str(repository_id))

    return Response(status_code=204)
