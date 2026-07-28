"""
FileAnalysisProgress ORM 模型

文件级分析进度实体，用于记录每个文件在各分析阶段的状态（R-R4）。

支持精确的断点续跑：恢复时仅重新解析未完成/失败的文件，跳过已成功处理的部分。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FileAnalysisProgressModel(Base):
    """
    文件级分析进度实体

    记录每个文件在每次分析任务中各阶段的处理状态。
    stage 枚举：scan / ast / structures / frameworks / ai / storing
    status 枚举：pending / processing / completed / failed / skipped
    """

    __tablename__ = "file_analysis_progress"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("analysis_versions.id", ondelete="CASCADE"), nullable=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    # R-R4: 冗余存储 file_path，便于在 files 表重建后仍能查询
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    # 分析阶段：scan / ast / structures / frameworks / ai / storing
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    # 处理状态：pending / processing / completed / failed / skipped
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # 进度附加数据：{nodes_count, edges_count, deps_count, error_message, ...}
    progress_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # R-R4: 核心索引 — (version_id, file_path, stage) 联合，精确查询某文件某阶段
        Index("idx_fap_version_file_stage", "analysis_version_id", "file_path", "stage"),
        # R-R4: 辅助索引 — 按阶段和状态查询
        Index("idx_fap_version_stage_status", "analysis_version_id", "stage", "status"),
        # R-R4: 按仓库和阶段查询
        Index("idx_fap_repo_stage_status", "repository_id", "stage", "status"),
        # R-R4: 部分唯一索引 — 同一版本+文件+阶段唯一
        Index(
            "uq_fap_version_file_stage",
            "analysis_version_id",
            "file_path",
            "stage",
            unique=True,
            postgresql_where=text("analysis_version_id IS NOT NULL"),
        ),
        CheckConstraint(
            "stage IN ('scan', 'ast', 'structures', 'frameworks', 'ai', 'storing')",
            name="chk_fap_stage",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'skipped')",
            name="chk_fap_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<FileAnalysisProgressModel(file={self.file_path}, stage={self.stage}, status={self.status})>"
