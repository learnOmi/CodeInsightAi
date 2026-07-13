"""
KnowledgePoint ORM 模型

知识点实体，包含 pgvector 向量嵌入。
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import UUID, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.config import settings
from codeinsight.db.base import Base


class KnowledgePointModel(Base):
    """
    知识点实体

    对应 Pydantic Schema: KnowledgePoint
    包含 pgvector 向量用于语义搜索。

    注意：Python 属性名使用 knowledge_metadata（避免与 SQLAlchemy 的 metadata 属性冲突），
    但数据库列名为 metadata（通过 mapped_column("metadata", ...) 指定）。
    Pydantic Schema 使用 Field(validation_alias="knowledge_metadata") 进行映射。
    """

    __tablename__ = "knowledge_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String, nullable=False)
    category_name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [])
    code_snippets: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [])
    call_chain: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [])
    expansion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {})
    embedding: Mapped[Vector | None] = mapped_column(Vector(settings.embedding_dimension), nullable=True)
    knowledge_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=lambda: {})
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "idx_knowledge_points_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_knowledge_points_tags", "tags", postgresql_using="gin"),
        Index("idx_knowledge_points_repository", "repository_id"),
        Index("idx_knowledge_points_repository_version", "repository_id", "version"),
        Index("idx_knowledge_points_category", "category"),
        Index("idx_knowledge_points_confidence", "confidence"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgePointModel(id={self.id}, title={self.title})>"
