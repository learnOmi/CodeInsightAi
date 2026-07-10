"""
AnalysisVersion ORM 模型

分析版本实体，用于追踪每次分析任务的结果。
"""

import uuid

from sqlalchemy import UUID, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class AnalysisVersionModel(Base):
    """
    分析版本实体

    对应 Pydantic Schema: AnalysisVersion
    记录每次分析任务的执行状态和结果统计。
    """

    __tablename__ = "analysis_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_points_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AnalysisVersionModel(id={self.id}, version={self.version})>"
