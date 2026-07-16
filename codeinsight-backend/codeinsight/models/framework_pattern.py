"""
FrameworkPattern ORM 模型

框架模式实体，存储框架检测过程中识别到的模式与置信度。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UUID, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FrameworkPatternModel(Base):
    """
    框架模式实体

    存储框架检测过程中识别到的模式，包含框架名、类别、置信度及证据。
    同一仓库 + 框架 + 分析版本下模式唯一。
    """

    __tablename__ = "framework_patterns"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("analysis_versions.id", ondelete="CASCADE"), nullable=True
    )
    # 框架检测信息
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=sa.text("0.0"))
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"))
    # 索引
    detected_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_framework_patterns_repo", "repository_id"),
        Index("idx_framework_patterns_version", "analysis_version_id"),
        # 唯一索引：同一仓库 + 框架 + 分析版本下模式唯一
        Index(
            "idx_framework_patterns_repo_fw_ver",
            "repository_id",
            "framework",
            "analysis_version_id",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FrameworkPatternModel(framework={self.framework}, "
            f"category={self.category}, confidence={self.confidence})>"
        )
