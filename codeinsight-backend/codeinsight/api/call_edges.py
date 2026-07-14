"""
调用边路由

提供调用图边的查询接口，供前端调用图可视化使用。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.analyzers.call_graph import CallGraphQuery
from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.models import CallEdgeModel
from codeinsight.repositories import AstNodeDAO, CallEdgeDAO
from codeinsight.schemas import CallEdge

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_call_edge_dao() -> CallEdgeDAO:
    """获取 CallEdgeDAO 实例（依赖注入）"""
    return CallEdgeDAO()


def get_ast_node_dao() -> AstNodeDAO:
    """获取 AstNodeDAO 实例（依赖注入）"""
    return AstNodeDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CallEdgeDaoDep = Annotated[CallEdgeDAO, Depends(get_call_edge_dao)]
AstNodeDaoDep = Annotated[AstNodeDAO, Depends(get_ast_node_dao)]


@router.get("/call-edges", response_model=list[CallEdge])
async def list_call_edges(
    db: DbSession,
    dao: CallEdgeDaoDep,
    file_id: Annotated[UUID | None, Query(description="文件 ID（按文件查询调用边）")] = None,
    repository_id: Annotated[UUID | None, Query(description="仓库 ID（按仓库查询调用边）")] = None,
    node_type: Annotated[str | None, Query(description="调用者节点类型过滤")] = None,
) -> list[CallEdge]:
    """
    获取调用边列表

    支持按文件、仓库、节点类型过滤。
    至少提供 file_id 或 repository_id 之一。
    """
    if file_id is not None:
        # 按文件查询：先获取该文件的所有节点 ID，再查询相关调用边
        ast_dao = get_ast_node_dao()
        file_nodes = await ast_dao.get_by_file(db, file_id)
        node_ids = {n.id for n in file_nodes}
        if not node_ids:
            return []

        from sqlalchemy import select

        edges = await db.execute(
            select(CallEdgeModel).where(
                CallEdgeModel.caller_node_id.in_(node_ids) | CallEdgeModel.callee_node_id.in_(node_ids)
            )
        )
        edge_models = list(edges.scalars().all())
    elif repository_id is not None:
        edge_models = await dao.get_by_repository(db, repository_id)
    else:
        return []

    # 按节点类型过滤（需要查询 caller 节点类型）
    if node_type is not None:
        filtered_edges = []
        ast_dao = get_ast_node_dao()
        for edge in edge_models:
            caller_node = await ast_dao.get_by_id(db, edge.caller_node_id)
            if caller_node and caller_node.node_type == node_type:
                filtered_edges.append(edge)
        edge_models = filtered_edges

    return [CallEdge.model_validate(e) for e in edge_models]


@router.get("/call-edges/{node_id}/callees")
async def get_callees(
    node_id: UUID,
    db: DbSession,
) -> list[dict]:
    """
    获取该节点调用的所有目标（正向调用图）

    返回调用边列表，每条边包含 caller 和 callee 节点信息。
    callee 为 None 时表示该调用无法匹配到具体目标（未知调用）。
    """
    query = CallGraphQuery()
    callees = await query.get_callees(node_id, db=db)
    return callees


@router.get("/call-edges/{node_id}/callers")
async def get_callers(
    node_id: UUID,
    db: DbSession,
) -> list[dict]:
    """
    获取调用该节点的所有调用者（反向调用图）

    返回调用边列表，每条边包含 caller 节点信息。
    """
    query = CallGraphQuery()
    callers = await query.get_callers(node_id, db=db)
    return callers


@router.get("/call-edges/{node_id}/chain")
async def get_call_chain(
    node_id: UUID,
    db: DbSession,
    max_depth: Annotated[int, Query(ge=1, le=20, description="最大遍历深度")] = 10,
) -> list[dict]:
    """
    获取从该节点开始的完整调用链（DFS 遍历）

    返回调用链节点列表，按深度排序。
    """
    query = CallGraphQuery()
    chain = await query.get_call_chain(node_id, max_depth=max_depth, db=db)
    return chain
