"""
仓库管理路由

提供仓库的增删改查接口。
"""

from typing import List

from fastapi import APIRouter
from codeinsight.schemas import Repository, RepositoryCreate, RepositoryUpdate

router = APIRouter()


@router.post("", response_model=Repository, status_code=201)
async def create_repository(request: RepositoryCreate):
    """
    添加代码仓库

    添加一个新的代码仓库并开始分析。
    """
    raise NotImplementedError("P1-07: 仓库创建接口待实现")


@router.get("", response_model=List[Repository])
async def list_repositories():
    """
    获取仓库列表

    分页返回用户的所有仓库。
    """
    raise NotImplementedError("P1-07: 仓库列表接口待实现")


@router.get("/{repository_id}", response_model=Repository)
async def get_repository(repository_id: str):
    """
    获取仓库详情
    """
    raise NotImplementedError("P1-07: 仓库详情接口待实现")


@router.put("/{repository_id}", response_model=Repository)
async def update_repository(repository_id: str, request: RepositoryUpdate):
    """
    更新仓库信息
    """
    raise NotImplementedError("P1-07: 仓库更新接口待实现")


@router.delete("/{repository_id}", status_code=200)
async def delete_repository(repository_id: str):
    """
    删除仓库及其所有分析数据
    """
    raise NotImplementedError("P1-07: 仓库删除接口待实现")
