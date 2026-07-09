"""
版本管理路由

提供分析版本的切换和回滚接口。
"""

from uuid import UUID

from fastapi import APIRouter, Query

from codeinsight.schemas import AnalysisVersion

router = APIRouter()


@router.get("/repositories/{repository_id}/versions", response_model=list[AnalysisVersion])
async def list_versions(repository_id: UUID):
    """获取分析版本列表"""
    raise NotImplementedError("P1-05: 版本列表接口待实现")


@router.post("/repositories/{repository_id}/switch-version")
async def switch_version(
    repository_id: UUID,
    version: str = Query(..., description="目标版本号"),
):
    """切换到指定版本"""
    raise NotImplementedError("P1-05: 版本切换接口待实现")


@router.post("/repositories/{repository_id}/rollback")
async def rollback_version(
    repository_id: UUID,
    version: str = Query(..., description="回滚目标版本"),
):
    """回滚到指定版本"""
    raise NotImplementedError("P1-05: 版本回滚接口待实现")
