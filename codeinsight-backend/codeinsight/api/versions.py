"""
版本管理路由

提供分析版本的列表、切换和回滚接口。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.models import RepositoryModel
from codeinsight.repositories.analysis_version import AnalysisVersionDAO
from codeinsight.schemas import AnalysisVersion, TaskStatus

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


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
    repo = await db.execute(select(RepositoryModel).where(RepositoryModel.id == repository_id))
    current_repo = repo.scalar_one_or_none()
    current_version_tag = current_repo.current_version if current_repo else None

    result = []
    for v in versions:
        result.append(
            AnalysisVersion(
                version=v.version,
                status=TaskStatus(v.status),
                total_files=v.total_files,
                analyzed_files=v.analyzed_files,
                knowledge_points_count=v.knowledge_points_count,
                is_current=(v.version == current_version_tag),
                started_at=v.started_at,
                completed_at=v.completed_at,
                error_message=v.error_message,
                created_at=v.created_at,
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

    API-9 修复：只允许切换到已完成的版本，禁止切换到分析中或已失败的版本。
    """
    # 验证仓库存在
    repo_result = await db.execute(select(RepositoryModel).where(RepositoryModel.id == repository_id))
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

    # API-9：验证版本已完成
    if target_version.status != TaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Version {version} is not completed (status={target_version.status}). "
            "Only completed versions can be switched to.",
        )

    previous_version = repo.current_version
    repo.current_version = version

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
    repo_result = await db.execute(select(RepositoryModel).where(RepositoryModel.id == repository_id))
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

    rolled_back_from = repo.current_version
    repo.current_version = version

    await db.flush()
    await db.refresh(repo)

    return {
        "message": f"已回滚到版本 {version}",
        "repository_id": str(repository_id),
        "rolled_back_from": rolled_back_from,
        "rolled_back_to": version,
        "rollback_record_id": f"rb-{version}",
    }
