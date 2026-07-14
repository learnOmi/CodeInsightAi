"""
AstNode ORM 模型

AST 节点实体，用于存储代码结构（函数、类、方法、导入等）。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UUID, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class AstNodeModel(Base):
    """
    AST 节点实体

    存储代码结构节点，支持父子关系（parent_node_id）。
    """

    __tablename__ = "ast_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    node_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_column: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="CASCADE"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=True)
    docstring: Mapped[str] = mapped_column(Text, nullable=True)
    # Phase 1 新增：框架感知字段
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb"))
    annotations: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    qualified_name: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AstNodeModel(id={self.id}, type={self.node_type}, name={self.name})>"

    __table_args__ = (
        # DB-1 修复：添加性能索引
        Index("idx_ast_nodes_repo_type", "repository_id", "node_type"),
        Index("idx_ast_nodes_repo_file", "repository_id", "file_id"),
        # Phase 1 新增：qualified_name 复合索引（调用图精确匹配）
        Index("idx_ast_nodes_qualified_name", "repository_id", "qualified_name"),
    )
