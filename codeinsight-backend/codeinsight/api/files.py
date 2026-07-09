"""
文件管理路由

提供文件的增删改查接口。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import get_db_session
from codeinsight.repositories.file import FileDAO
from codeinsight.schemas import File, FileCreate, FileUpdate

router = APIRouter()


def get_file_dao() -> FileDAO:
    """获取 FileDAO 实例（依赖注入）"""
    return FileDAO()


@router.post("", response_model=File, status_code=201)
async def create_file(
    request: FileCreate,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: FileDAO = Depends(get_file_dao),  # noqa: B008
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
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: FileDAO = Depends(get_file_dao),  # noqa: B008
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
    repository_id: UUID = Query(..., description="仓库 ID"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: FileDAO = Depends(get_file_dao),  # noqa: B008
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
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: FileDAO = Depends(get_file_dao),  # noqa: B008
):
    """
    更新文件信息
    """
    existing = await dao.get_by_id(db, file_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    file_obj = await dao.update(db, file_id, request)
    return file_obj


@router.delete("/{file_id}", response_model=BaseModel, status_code=200)
async def delete_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: FileDAO = Depends(get_file_dao),  # noqa: B008
):
    """
    删除文件
    """
    deleted = await dao.delete(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    return BaseModel()