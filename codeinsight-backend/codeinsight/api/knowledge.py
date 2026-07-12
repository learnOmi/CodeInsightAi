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

    # Convert ORM models to Pydantic schemas for PaginatedKnowledgePoints
    items = [KnowledgePoint.model_validate(p) for p in points]

    return PaginatedKnowledgePoints(
        items=items,
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
    优化：9 次独立查询合并为 3 次（分类 GROUP BY + 总数 + 置信度 GROUP BY）。
    """
    from codeinsight.schemas import KnowledgeCategory

    # 构建 version 过滤条件（version=None 时不加过滤）
    version_condition = (KnowledgePointModel.version == version) if version is not None else None

    def _where_base() -> list:
        conditions = [KnowledgePointModel.repository_id == repository_id]
        if version_condition is not None:
            conditions.append(version_condition)
        return conditions

    # 1 次查询：按分类分组计数
    by_category_result = await db.execute(
        select(
            KnowledgePointModel.category,
            func.count(KnowledgePointModel.id),
        )
        .where(*_where_base())
        .group_by(KnowledgePointModel.category)
    )

    _category_enum_map = {
        KnowledgeCategory.DESIGN_PATTERN.value: KnowledgeCategory.DESIGN_PATTERN,
        KnowledgeCategory.ARCHITECTURE_DECISION.value: KnowledgeCategory.ARCHITECTURE_DECISION,
        KnowledgeCategory.ALGORITHM.value: KnowledgeCategory.ALGORITHM,
        KnowledgeCategory.ENGINEERING_TIP.value: KnowledgeCategory.ENGINEERING_TIP,
        KnowledgeCategory.DOMAIN_KNOWLEDGE.value: KnowledgeCategory.DOMAIN_KNOWLEDGE,
    }

    by_category: dict[KnowledgeCategory, int] = {}
    for category, count in by_category_result.tuples():
        if count > 0 and category in _category_enum_map:
            by_category[_category_enum_map[category]] = count

    # 1 次查询：总记录数
    total_result = await db.execute(select(func.count(KnowledgePointModel.id)).where(*_where_base()))
    total_points = total_result.scalar() or 0

    # 1 次查询：按置信度分组计数
    confidence_result = await db.execute(
        select(
            KnowledgePointModel.confidence,
            func.count(KnowledgePointModel.id),
        )
        .where(*_where_base())
        .group_by(KnowledgePointModel.confidence)
    )

    by_confidence: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for confidence, count in confidence_result.tuples():
        if confidence is not None:
            if confidence >= 0.8:
                by_confidence["high"] += count
            elif confidence >= 0.5:
                by_confidence["medium"] += count
            else:
                by_confidence["low"] += count

    return KnowledgeStats(
        total_points=total_points,
        by_category=by_category,
        by_confidence=by_confidence,
    )
