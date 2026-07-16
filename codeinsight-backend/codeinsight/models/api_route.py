"""
ApiRoute ORM 模型

API 路由实体，存储框架感知检测到的 HTTP API 端点信息。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UUID, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class ApiRouteModel(Base):
    """
    API 路由实体

    存储框架感知检测到的 HTTP API 端点信息，包括 HTTP 方法、路径模式、处理函数等。
    ast_node_id 可为 None（处理函数未匹配到 AST 节点时）。
    """

    __tablename__ = "api_routes"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("analysis_versions.id", ondelete="CASCADE"), nullable=True
    )
    ast_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="SET NULL"), nullable=True
    )
    # 路由信息
    http_method: Mapped[str] = mapped_column(String(8), nullable=False)
    path_pattern: Mapped[str] = mapped_column(String(1024), nullable=False)
    handler_function: Mapped[str] = mapped_column(String(256), nullable=False)
    handler_file: Mapped[str] = mapped_column(String(1024), nullable=False)
    middlewares: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    # 索引
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_api_routes_repo", "repository_id"),
        Index("idx_api_routes_version", "analysis_version_id"),
        Index("idx_api_routes_method_path", "repository_id", "http_method", "path_pattern"),
    )

    def __repr__(self) -> str:
        return f"<ApiRouteModel(method={self.http_method}, path={self.path_pattern}, handler={self.handler_function})>"
