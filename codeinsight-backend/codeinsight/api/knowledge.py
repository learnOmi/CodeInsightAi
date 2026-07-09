"""
知识点查询路由

提供知识点的列表、详情、统计接口。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.db.session import get_db_session
from codeinsight.models import KnowledgePointModel
from codeinsight.repositories.knowledge_point import KnowledgePointDAO
from codeinsight.schemas import (
    KnowledgePoint,
    KnowledgeStats,
    PaginatedKnowledgePoints,
)

router = APIRouter()


def get_knowledge_point_dao() -> KnowledgePointDAO:
    """获取 KnowledgePointDAO 实例（依赖注入）"""
    return KnowledgePointDAO()


@router.get("/knowledge-points", response_model=PaginatedKnowledgePoints)
async def list_knowledge_points(
    repository_id: UUID = Query(..., description="仓库 ID"),  # noqa: B008
    version: str | None = Query(None, description="分析版本号，不传则使用当前版本"),
    category: str | None = Query(None, description="按分类筛选：DP-/AD-/AL-/ET-/DK-"),
    tag: str | None = Query(None, description="按标签筛选"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query(default="created_at", description="排序字段：created_at/title/confidence"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$", description="排序方向"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: KnowledgePointDAO = Depends(get_knowledge_point_dao),  # noqa: B008
):
    """
    获取知识点列表

    分页返回指定仓库的知识点列表，支持按版本、分类、标签筛选。
    """
    skip = (page - 1) * page_size

    points = await dao.list(
        db=db,
        repository_id=repository_id,
        version=version,
        category=category,
        tag=tag,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    total = await dao.count(
        db=db,
        repository_id=repository_id,
        version=version,
        category=category,
    )

    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedKnowledgePoints(
        items=points,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/knowledge-points/{point_id}", response_model=KnowledgePoint)
async def get_knowledge_point(
    point_id: UUID,
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: KnowledgePointDAO = Depends(get_knowledge_point_dao),  # noqa: B008
):
    """
    获取知识点详情

    根据 ID 获取单个知识点的完整信息，包括代码片段、调用链、拓展内容等。
    """
    kp = await dao.get_by_id(db, point_id)

    if kp is None:
        raise HTTPException(status_code=404, detail=f"KnowledgePoint {point_id} not found")

    return kp


@router.get("/repositories/{repository_id}/knowledge-stats", response_model=KnowledgeStats)
async def get_knowledge_stats(
    repository_id: UUID,
    version: str | None = Query(None, description="分析版本号，不传则使用当前版本"),
    db: AsyncSession = Depends(get_db_session),  # noqa: B008
    dao: KnowledgePointDAO = Depends(get_knowledge_point_dao),  # noqa: B008
):
    """
    获取知识点统计

    返回指定仓库的知识点统计数据，包括按分类分布、置信度分布、热门标签等。
    """
    total_points = await dao.count(db=db, repository_id=repository_id, version=version)

    # 按分类统计
    by_category: dict[str, int] = {}
    for cat in ["DP-", "AD-", "AL-", "ET-", "DK-"]:
        count = await dao.count(db=db, repository_id=repository_id, version=version, category=cat)
        if count > 0:
            by_category[cat] = count

    # 按置信度区间统计
    by_confidence: dict[str, int] = {"high": 0, "medium": 0, "low": 0}

    high_result = await db.execute(
        select(func.count(KnowledgePointModel.id)).where(
            KnowledgePointModel.repository_id == repository_id,
            KnowledgePointModel.confidence >= 0.8,
        )
    )
    by_confidence["high"] = high_result.scalar() or 0

    medium_result = await db.execute(
        select(func.count(KnowledgePointModel.id)).where(
            KnowledgePointModel.repository_id == repository_id,
            KnowledgePointModel.confidence >= 0.5,
            KnowledgePointModel.confidence < 0.8,
        )
    )
    by_confidence["medium"] = medium_result.scalar() or 0

    low_result = await db.execute(
        select(func.count(KnowledgePointModel.id)).where(
            KnowledgePointModel.repository_id == repository_id,
            KnowledgePointModel.confidence < 0.5,
        )
    )
    by_confidence["low"] = low_result.scalar() or 0

    return KnowledgeStats(
        total_points=total_points,
        by_category=by_category,
        by_confidence=by_confidence,
    )
