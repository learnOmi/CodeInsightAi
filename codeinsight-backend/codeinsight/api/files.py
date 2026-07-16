"""
文件管理路由

提供文件的增删改查接口。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.models import FileModel
from codeinsight.repositories.file import FileDAO
from codeinsight.schemas import File, FileCreate, FileUpdate

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_file_dao() -> FileDAO:
    """获取 FileDAO 实例（依赖注入）"""
    return FileDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
FileDaoDep = Annotated[FileDAO, Depends(get_file_dao)]
RepositoryIdQuery = Annotated[UUID, Query(description="仓库 ID")]


@router.get("")
async def list_files(
    repository_id: RepositoryIdQuery,
    db: DbSession,
    dao: FileDaoDep,
    page: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, description="每页数量")] = 100,
):
    """
    获取文件列表（分页）
    """
    skip = (page - 1) * page_size
    files = await dao.list_by_repository(db, repository_id, skip=skip, limit=page_size)

    total_files = await db.execute(select(func.count()).where(FileModel.repository_id == repository_id))
    total = total_files.scalar() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)

    items = [File.model_validate(f) for f in files]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("", response_model=File, status_code=201)
async def create_file(
    request: FileCreate,
    db: DbSession,
    dao: FileDaoDep,
):
    """
    添加代码文件

    在指定仓库下添加一个新文件。
    """
    file_obj = await dao.create(db, request)
    return file_obj


@router.get("/{file_id}", response_model=File)
async def get_file(
    file_id: UUID,
    db: DbSession,
    dao: FileDaoDep,
):
    """
    获取文件详情
    """
    file_obj = await dao.get_by_id(db, file_id)

    if file_obj is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    return file_obj


@router.get("/by-hash/{content_hash}", response_model=list[File])
async def get_files_by_hash(
    content_hash: str,
    repository_id: RepositoryIdQuery,
    db: DbSession,
    dao: FileDaoDep,
):
    """
    根据内容哈希查找文件（用于增量检测）
    """
    file_obj = await dao.get_by_content_hash(db, repository_id, content_hash)
    if file_obj is None:
        return []
    return [file_obj]


@router.put("/{file_id}", response_model=File)
async def update_file(
    file_id: UUID,
    request: FileUpdate,
    db: DbSession,
    dao: FileDaoDep,
):
    """
    更新文件信息
    """
    existing = await dao.get_by_id(db, file_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    file_obj = await dao.update(db, file_id, request)
    return file_obj


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: UUID,
    db: DbSession,
    dao: FileDaoDep,
):
    """
    删除文件
    """
    deleted = await dao.delete(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    return Response(status_code=204)
