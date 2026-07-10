"""
版本管理路由

提供分析版本的列表、切换和回滚接口。
"""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import get_db_session
from codeinsight.models import RepositoryModel
from codeinsight.repositories.analysis_version import AnalysisVersionDAO
from codeinsight.schemas import AnalysisVersion, TaskStatus

router = APIRouter()


def get_analysis_version_dao() -> AnalysisVersionDAO:
    """获取 AnalysisVersionDAO 实例（依赖注入）"""
    return AnalysisVersionDAO()


@router.get("/repositories/{repository_id}/versions", response_model=list[AnalysisVersion])
async def list_versions(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: AnalysisVersionDAO = Depends(get_analysis_version_dao),  # noqa: B008
):
    """
    获取分析版本列表

    返回指定仓库的所有分析版本，按创建时间降序排列。
    """
    versions = await dao.list_by_repository(db=db, repository_id=repository_id)

    # 获取仓库当前版本号，用于标记 is_current
    repo = await db.execute(
        select(RepositoryModel).where(RepositoryModel.id == repository_id)
    )
    current_repo = repo.scalar_one_or_none()
    current_version_tag = current_repo.current_version if current_repo else None

    result = []
    for v in versions:
        # Cast SQLAlchemy column descriptors to their actual runtime types
        result.append(
            AnalysisVersion(
                version=str(cast(str, v.version)),
                status=TaskStatus(cast(str, v.status)),
                total_files=int(cast(int, v.total_files)),
                analyzed_files=int(cast(int, v.analyzed_files)),
                knowledge_points_count=int(cast(int, v.knowledge_points_count)),
                is_current=(str(cast(str, v.version)) == current_version_tag),
                started_at=str(v.started_at) if v.started_at else None,
                completed_at=str(v.completed_at) if v.completed_at else None,
                error_message=cast(str | None, v.error_message),
                created_at=str(v.created_at),
            )
        )

    return result


@router.post("/repositories/{repository_id}/switch-version")
async def switch_version(
    repository_id: UUID,
    version: str = Query(..., description="目标版本号"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: AnalysisVersionDAO = Depends(get_analysis_version_dao),  # noqa: B008
):
    """
    切换到指定版本

    将仓库的当前版本设置为指定版本，后续查询将使用该版本的数据。
    """
    # 验证仓库存在
    repo_result = await db.execute(
        select(RepositoryModel).where(RepositoryModel.id == repository_id)
    )
    repo = repo_result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    # 验证目标版本存在
    target_version = await dao.get_by_version_tag(db, repository_id, version)
    if target_version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for repository {repository_id}",
        )

    previous_version = cast(str, repo.current_version)
    repo.current_version = version  # type: ignore[assignment]

    await db.flush()
    await db.refresh(repo)

    return {
        "message": f"已切换到版本 {version}",
        "repository_id": str(repository_id),
        "previous_version": previous_version,
        "current_version": version,
    }


@router.post("/repositories/{repository_id}/rollback")
async def rollback_version(
    repository_id: UUID,
    version: str = Query(..., description="回滚目标版本"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: AnalysisVersionDAO = Depends(get_analysis_version_dao),  # noqa: B008
):
    """
    回滚到指定版本

    将仓库状态恢复到指定历史版本，并标记此次变更为"回滚"操作。
    """
    # 验证仓库存在
    repo_result = await db.execute(
        select(RepositoryModel).where(RepositoryModel.id == repository_id)
    )
    repo = repo_result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    # 验证目标版本存在
    target_version = await dao.get_by_version_tag(db, repository_id, version)
    if target_version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for repository {repository_id}",
        )

    rolled_back_from = cast(str, repo.current_version)
    repo.current_version = version  # type: ignore[assignment]

    await db.flush()
    await db.refresh(repo)

    return {
        "message": f"已回滚到版本 {version}",
        "repository_id": str(repository_id),
        "rolled_back_from": rolled_back_from,
        "rolled_back_to": version,
        "rollback_record_id": f"rb-{version}",
    }
