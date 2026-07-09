"""
File ORM 模型

代码文件实体，用于追踪仓库中的所有源代码文件。
"""

import uuid

from sqlalchemy import UUID, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class FileModel(Base):
    """
    文件实体

    追踪仓库中的源代码文件，用于增量分析检测。
    """

    __tablename__ = "files"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    path = Column(String, nullable=False)
    absolute_path = Column(String, nullable=False)
    language = Column(String, nullable=False)
    line_count = Column(Integer, nullable=False, default=0)
    size_bytes = Column(Integer, nullable=False, default=0)
    content_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FileModel(id={self.id}, path={self.path})>"
