"""
Repository ORM 模型

仓库实体，与 Pydantic Schema 对齐但使用数据库原生类型。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class RepositoryModel(Base):
    """
    仓库实体

    对应 Pydantic Schema: Repository
    """

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    current_version: Mapped[str | None] = mapped_column(String, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_points_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {})
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())
    last_analyzed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # M-5: CHECK 约束限制状态值，防止脏数据
        CheckConstraint(
            "status IN ('pending', 'analyzing', 'analyzing_structures', 'completed', 'failed')",
            name="chk_repository_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<RepositoryModel(id={self.id}, name={self.name})>"
