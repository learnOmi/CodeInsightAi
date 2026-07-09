"""
KnowledgePoint ORM 模型

知识点实体，包含 pgvector 向量嵌入。
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import UUID, Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class KnowledgePointModel(Base):
    """
    知识点实体

    对应 Pydantic Schema: KnowledgePoint
    包含 pgvector 向量用于语义搜索。

    注意：Python 属性名使用 knowledge_metadata（避免与 SQLAlchemy 的 metadata 属性冲突），
    但数据库列名为 metadata（通过 Column("metadata", ...) 指定）。
    Pydantic Schema 使用 Field(validation_alias="knowledge_metadata") 进行映射。
    """

    __tablename__ = "knowledge_points"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    version = Column(String, nullable=False)
    repository_id = Column(UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)
    category_name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    tags = Column(JSONB, nullable=False, default=lambda: [])
    code_snippets = Column(JSONB, nullable=False, default=lambda: [])
    call_chain = Column(JSONB, nullable=False, default=lambda: [])
    expansion = Column(JSONB, nullable=False, default=lambda: {})
    embedding = Column(Vector(1536), nullable=True)
    knowledge_metadata = Column("metadata", JSONB, nullable=False, default=lambda: {})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<KnowledgePointModel(id={self.id}, title={self.title})>"
