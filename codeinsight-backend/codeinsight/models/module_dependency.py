"""
ModuleDependency ORM 模型

模块依赖实体，存储模块间依赖关系：importer（导入者）→ imported（被导入者）。
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class ModuleDependencyModel(Base):
    """
    模块依赖实体

    存储模块间依赖关系。imported_file_id 可为 None（外部库或未匹配）。
    """

    __tablename__ = "module_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    importer_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    imported_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    # 导入信息
    import_name: Mapped[str] = mapped_column(String, nullable=False)
    import_type: Mapped[str] = mapped_column(String, nullable=False, default="absolute")
    # 索引
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "import_type IN ('relative', 'absolute', 'external')",
            name="chk_import_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<ModuleDependencyModel(importer={self.importer_file_id}, imported={self.imported_file_id}, name={self.import_name})>"
