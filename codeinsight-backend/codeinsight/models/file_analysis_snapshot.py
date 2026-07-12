"""
FileAnalysisSnapshot ORM 模型

文件分析快照实体，用于存储每次分析的文件内容哈希，支持增量分析。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FileAnalysisSnapshotModel(Base):
    """
    文件分析快照实体

    存储每次分析时每个文件的内容哈希，作为增量分析的基准。
    支持通过 analysis_version 关联到对应的分析版本。
    """

    __tablename__ = "file_analysis_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String, nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    nodes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deps_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        # 同一仓库+版本+文件的快照唯一
        UniqueConstraint("repository_id", "analysis_version", "file_id", name="uq_snapshot_file_version"),
        # 索引：按 content_hash 查找（增量检测用）
        Index("idx_snapshot_content_hash", "content_hash"),
        CheckConstraint(
            "content_hash IS NOT NULL AND length(content_hash) > 0",
            name="chk_snapshot_content_hash",
        ),
    )

    def __repr__(self) -> str:
        short_hash = self.content_hash[:12]
        return f"<FileAnalysisSnapshotModel(id={self.id}, version={self.analysis_version}, hash={short_hash}...)>"
