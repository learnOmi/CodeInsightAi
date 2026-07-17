"""
搜索路由

提供代码的全局文本搜索功能（基于 SQL 模糊匹配，不涉及 AI/向量搜索）。
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.models import AstNodeModel, FileModel

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/search/nodes")
async def search_nodes(
    q: str,
    db: DbSession,
    repository_id: Annotated[UUID | None, Query(description="限定搜索的仓库")] = None,
    node_type: Annotated[str | None, Query(description="限定节点类型（function/class/method 等）")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="返回条数上限")] = 20,
):
    """
    全局搜索 AST 节点

    按名称模糊搜索代码中的类、函数、方法等 AST 节点。
    基于 SQL ILIKE 模糊匹配，不涉及 AI。
    """
    query = select(AstNodeModel).where(AstNodeModel.name.ilike(f"%{q}%"))

    if repository_id:
        query = query.where(AstNodeModel.repository_id == repository_id)
    if node_type:
        query = query.where(AstNodeModel.node_type == node_type)

    query = query.order_by(AstNodeModel.name).limit(limit)
    result = await db.execute(query)
    nodes = result.scalars().all()

    return [
        {
            "id": str(n.id),
            "repositoryId": str(n.repository_id),
            "fileId": str(n.file_id),
            "nodeType": n.node_type,
            "name": n.name,
            "filePath": n.file_path,
            "language": n.language,
            "qualifiedName": n.qualified_name,
            "startLine": n.start_line,
            "endLine": n.end_line,
            "tags": n.tags or [],
        }
        for n in nodes
    ]


@router.get("/search/files")
async def search_files(
    q: str,
    db: DbSession,
    repository_id: Annotated[UUID | None, Query(description="限定搜索的仓库")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="返回条数上限")] = 20,
):
    """
    全局搜索文件

    按路径模糊匹配文件名。
    """
    query = select(FileModel).where(FileModel.path.ilike(f"%{q}%"))

    if repository_id:
        query = query.where(FileModel.repository_id == repository_id)

    query = query.order_by(FileModel.path).limit(limit)
    result = await db.execute(query)
    files = result.scalars().all()

    return [
        {
            "id": str(f.id),
            "repositoryId": str(f.repository_id),
            "path": f.path,
            "language": f.language,
            "lineCount": f.line_count,
        }
        for f in files
    ]


@router.get("/search/suggestions")
async def search_suggestions(
    q: str,
    db: DbSession,
    repository_id: Annotated[UUID | None, Query(description="限定搜索的仓库")] = None,
    limit: Annotated[int, Query(ge=1, le=20, description="返回建议条数上限")] = 10,
):
    """
    获取搜索建议（自动补全）

    基于 AST 节点名前缀匹配，返回搜索建议列表。
    """
    if not q or len(q) < 1:
        return {"query": q, "suggestions": []}

    query = (
        select(
            AstNodeModel.name,
            AstNodeModel.node_type,
            func.count().label("cnt"),
        )
        .where(
            AstNodeModel.name.ilike(f"{q}%"),
            AstNodeModel.node_type.in_(["function", "method", "class", "interface"]),
        )
        .group_by(AstNodeModel.name, AstNodeModel.node_type)
        .order_by(func.count().desc())
        .limit(limit)
    )

    if repository_id:
        query = query.where(AstNodeModel.repository_id == repository_id)

    result = await db.execute(query)
    rows = result.all()

    suggestions = [{"text": row[0], "type": row[1], "count": row[2]} for row in rows]

    return {"query": q, "suggestions": suggestions}
