"""
仓库管理路由

提供仓库的增删改查接口。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import get_db_session
from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import Repository, RepositoryCreate, RepositoryUpdate

router = APIRouter()


def get_repository_dao() -> RepositoryDAO:
    """获取 RepositoryDAO 实例（依赖注入）"""
    return RepositoryDAO()


@router.post("", response_model=Repository, status_code=201)
async def create_repository(
    request: RepositoryCreate,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
):
    """
    添加代码仓库

    添加一个新的代码仓库并开始分析。
    """
    # 检查路径是否已存在
    if await dao.exists_by_path(db, request.path):
        raise HTTPException(status_code=409, detail=f"Repository path already exists: {request.path}")

    repo = await dao.create(db, request)
    return repo


@router.get("", response_model=list[Repository])
async def list_repositories(
    skip: int = Query(default=0, ge=0, description="跳过的记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回的记录数"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
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
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
):
    """
    获取仓库详情
    """
    repo = await dao.get_by_id(db, repository_id)

    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    return repo


@router.put("/{repository_id}", response_model=Repository)
async def update_repository(
    repository_id: UUID,
    request: RepositoryUpdate,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
):
    """
    更新仓库信息
    """
    # 检查仓库是否存在
    existing = await dao.get_by_id(db, repository_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    repo = await dao.update(db, repository_id, request)
    return repo


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: RepositoryDAO = Depends(get_repository_dao),  # noqa: B008
):
    """
    删除仓库及其所有分析数据
    """
    deleted = await dao.delete(db, repository_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    return Response(status_code=204)
