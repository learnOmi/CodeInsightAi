"""
AST 节点路由

提供 AST 节点的查询接口，供前端结构概览使用。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories.ast_node import AstNodeDAO
from codeinsight.schemas.ast_node import AstNode

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_ast_node_dao() -> AstNodeDAO:
    """获取 AstNodeDAO 实例（依赖注入）"""
    return AstNodeDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AstNodeDaoDep = Annotated[AstNodeDAO, Depends(get_ast_node_dao)]


@router.get("")
async def list_ast_nodes(
    db: DbSession,
    dao: AstNodeDaoDep,
    file_id: Annotated[UUID | None, Query(description="文件 ID（按文件查询节点）")] = None,
    repository_id: Annotated[UUID | None, Query(description="仓库 ID（按仓库查询节点）")] = None,
    node_type: Annotated[str | None, Query(description="节点类型过滤")] = None,
) -> list[AstNode]:
    """
    获取 AST 节点列表

    支持按文件、仓库、节点类型过滤。
    至少提供 file_id 或 repository_id 之一。
    """
    if file_id is not None:
        nodes = await dao.get_by_file(db, file_id)
    elif repository_id is not None:
        nodes = await dao.get_by_repository(db, repository_id)
    else:
        return []

    if node_type is not None:
        nodes = [n for n in nodes if n.node_type == node_type]

    return [AstNode.model_validate(n) for n in nodes]


@router.get("/{node_id}", response_model=AstNode)
async def get_ast_node(
    node_id: UUID,
    db: DbSession,
    dao: AstNodeDaoDep,
) -> AstNode:
    """获取单个 AST 节点详情"""
    node = await dao.get_by_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"AST node {node_id} not found")
    return AstNode.model_validate(node)
