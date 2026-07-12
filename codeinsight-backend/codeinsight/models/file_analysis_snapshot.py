"""
FileAnalysisSnapshot ORM 模型

文件分析快照实体，用于存储每次分析的文件内容哈希，支持增量分析。

外键策略（无 CASCADE）：
- repository_id → repositories.id: ondelete=CASCADE（仓库删除时级联）
- file_id → files.id: ondelete=SET NULL, nullable=True（不级联，由业务逻辑管理）
  原因：每次 _store_files_to_db 会 DELETE+INSERT files 表（UUID 变化），
  若设 CASCADE 则所有历史快照被级联删除，导致增量分析基准永久丢失。
  现在改为 SET NULL，历史快照的 file_id 被置空但记录保留；
  content_hash 作为增量分析的实际基准，不受 file_id 影响。
  SnapshotManager._cleanup_old_snapshots 按版本策略清理过期快照。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FileAnalysisSnapshotModel(Base):
    """
    文件分析快照实体

    存储每次分析时每个文件的内容哈希，作为增量分析的基准。
    支持通过 analysis_version 关联到对应的分析版本。

    file_id 设计说明：
    - nullable=True + ondelete=SET NULL：历史快照不受 files 表重建影响
    - content_hash 是增量分析的实际基准（通过 content_hash 对比判断变更）
    - file_id 仅用于关联文件元数据（path, language），文件已删除时为 NULL
    """

    __tablename__ = "file_analysis_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String, nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    nodes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deps_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        # 索引：按 (repo, version) 查找快照（增量分析用）
        Index("idx_snapshot_repo_version", "repository_id", "analysis_version"),
        # 索引：按 content_hash 查找（增量检测用）
        Index("idx_snapshot_content_hash", "content_hash"),
        # 部分唯一索引：仅 file_id 非空时唯一
        # PostgreSQL 中 NULL ≠ NULL，但复合唯一约束中 NULL 被视为相等
        # 使用 partial index 避免 SET NULL 后多条 NULL 记录冲突
        Index(
            "uq_snapshot_repo_version_file_partial",
            "repository_id",
            "analysis_version",
            "file_id",
            unique=True,
            postgresql_where=text("file_id IS NOT NULL"),
        ),
        CheckConstraint(
            "content_hash IS NOT NULL AND length(content_hash) > 0",
            name="chk_snapshot_content_hash",
        ),
    )

    def __repr__(self) -> str:
        short_hash = self.content_hash[:12]
        return f"<FileAnalysisSnapshotModel(id={self.id}, version={self.analysis_version}, hash={short_hash}...)>"
