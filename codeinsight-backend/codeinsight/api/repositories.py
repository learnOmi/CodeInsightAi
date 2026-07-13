"""
仓库管理路由

提供仓库的增删改查接口。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.exceptions import RepositoryNotFoundError, RepositoryPathExistsError
from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import Repository, RepositoryCreate, RepositoryUpdate

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

    添加一个新的代码仓库并开始分析。
    """
    # 检查路径是否已存在
    if await dao.exists_by_path(db, request.path):
        raise RepositoryPathExistsError(request.path)

    repo = await dao.create(db, request)
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
