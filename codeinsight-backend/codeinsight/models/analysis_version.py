"""
AnalysisVersion ORM 模型

分析版本实体，用于追踪每次分析任务的结果。
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, UUID, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_points_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        # 同一仓库内版本标签唯一（而非全局唯一）
        UniqueConstraint("repository_id", "version", name="uq_repository_version"),
        # 索引：按仓库+创建时间排序
        Index("idx_analysis_versions_repository_created", "repository_id", "created_at"),
        # 状态字段限制
        CheckConstraint(
            "status IN ('pending', 'scanning', 'parsing', 'analyzing_structures', "
            "'analyzing_modules', 'storing', 'completed', 'failed', 'cancelled')",
            name="chk_analysis_version_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<AnalysisVersionModel(id={self.id}, version={self.version})>"
