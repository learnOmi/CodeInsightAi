"""
ExternalDependency ORM 模型

外部依赖实体，存储从依赖声明文件（pom.xml、package.json、requirements.txt 等）
中解析出的第三方依赖信息。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UUID, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class ExternalDependencyModel(Base):
    """
    外部依赖实体

    存储项目声明的第三方依赖信息，支持多种生态系统（Maven、NPM、Pip、Go 等）。
    每个依赖关联到具体的声明文件和仓库。
    """

    __tablename__ = "external_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("analysis_versions.id", ondelete="CASCADE"), nullable=True
    )
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    artifact_name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="compile", server_default="compile")
    declaration_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    used_by_files: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_external_deps_repo", "repository_id"),
        Index("idx_external_deps_version", "analysis_version_id"),
        Index("idx_external_deps_ecosystem", "repository_id", "ecosystem"),
    )

    def __repr__(self) -> str:
        group = f"{self.group_name}/" if self.group_name else ""
        return f"<ExternalDependencyModel({self.ecosystem}: {group}{self.artifact_name}@{self.version})>"
