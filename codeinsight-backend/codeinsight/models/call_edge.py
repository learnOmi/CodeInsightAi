"""
CallEdge ORM 模型

调用边实体，存储函数调用关系：caller（调用者）→ callee（被调用者）。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class CallEdgeModel(Base):
    """
    调用边实体

    存储函数调用关系。callee_node_id 可为 None（未知调用或动态调用无法匹配）。
    """

    __tablename__ = "call_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    caller_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="CASCADE"), nullable=False
    )
    callee_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("ast_nodes.id", ondelete="SET NULL"), nullable=True
    )
    # 调用位置
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(Integer, nullable=False)
    # 调用信息
    call_name: Mapped[str] = mapped_column(String, nullable=False)
    call_type: Mapped[str] = mapped_column(String, nullable=False, default="static")
    # 索引
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "call_type IN ('static', 'dynamic', 'unknown')",
            name="chk_call_type",
        ),
        # DB-2 修复：添加 repository_id 索引
        Index("idx_call_edges_repository", "repository_id"),
    )

    def __repr__(self) -> str:
        return f"<CallEdgeModel(caller={self.caller_node_id}, callee={self.callee_node_id}, name={self.call_name})>"
