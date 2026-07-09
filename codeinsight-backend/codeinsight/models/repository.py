"""
Repository ORM 模型

仓库实体，与 Pydantic Schema 对齐但使用数据库原生类型。
"""

import uuid

from sqlalchemy import UUID, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class RepositoryModel(Base):
    """
    仓库实体

    对应 Pydantic Schema: Repository
    """

    __tablename__ = "repositories"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending")
    current_version = Column(String, nullable=True)
    file_count = Column(Integer, nullable=False, default=0)
    line_count = Column(Integer, nullable=False, default=0)
    knowledge_points_count = Column(Integer, nullable=False, default=0)
    language_distribution = Column(JSONB, nullable=False, default=lambda: {})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<RepositoryModel(id={self.id}, name={self.name})>"
