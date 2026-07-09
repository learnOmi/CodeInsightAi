"""
AnalysisVersion ORM 模型

分析版本实体，用于追踪每次分析任务的结果。
"""

import uuid

from sqlalchemy import UUID, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from codeinsight.db.base import Base


class AnalysisVersionModel(Base):
    """
    分析版本实体

    对应 Pydantic Schema: AnalysisVersion
    记录每次分析任务的执行状态和结果统计。
    """

    __tablename__ = "analysis_versions"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    version = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending")
    total_files = Column(Integer, nullable=False, default=0)
    analyzed_files = Column(Integer, nullable=False, default=0)
    knowledge_points_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AnalysisVersionModel(id={self.id}, version={self.version})>"
