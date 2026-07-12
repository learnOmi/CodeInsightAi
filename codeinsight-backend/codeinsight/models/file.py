"""
File ORM 模型

代码文件实体，用于追踪仓库中的所有源代码文件。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FileModel(Base):
    """
    文件实体

    追踪仓库中的源代码文件，用于增量分析检测。
    """

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # 同一仓库内路径唯一
        UniqueConstraint("repository_id", "path", name="uq_repository_file_path"),
        # 复合索引：文件列表查询
        Index("idx_files_repository_path", "repository_id", "path"),
        # 索引：增量分析按 content_hash 查找
        Index("idx_files_content_hash", "content_hash"),
    )

    def __repr__(self) -> str:
        return f"<FileModel(id={self.id}, path={self.path})>"
