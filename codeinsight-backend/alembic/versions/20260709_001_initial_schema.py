"""
Initial database schema migration.

Creates all core tables for CodeInsight AI:
- repositories
- files
- knowledge_points (with pgvector vector column)
- analysis_versions

Also creates pgvector extension for vector search and indexes for query performance.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260709_001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 pgvector 扩展（必须在使用 vector 类型之前执行）
    # pgvector 提供向量类型和相似度搜索功能，用于 knowledge_points 表的 embedding 列
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "repositories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("current_version", sa.String(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("knowledge_points_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("language_distribution", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )

    op.create_table(
        "files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("absolute_path", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "analysis_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analyzed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("knowledge_points_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
    )

    # 使用原生 SQL 创建 knowledge_points 表
    # 原因：knowledge_points 包含 pgvector 的 vector(1536) 自定义类型，
    # Alembic 的 op.create_table() API 对这种第三方扩展类型支持不完善，
    # 使用原生 SQL 确保向量类型定义和维度参数完全正确
    op.execute(
        """
        CREATE TABLE knowledge_points (
            id UUID PRIMARY KEY,
            version TEXT NOT NULL,
            repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            category_name TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            confidence FLOAT NOT NULL DEFAULT 0.0,
            tags JSONB NOT NULL DEFAULT '[]',
            code_snippets JSONB NOT NULL DEFAULT '[]',
            call_chain JSONB NOT NULL DEFAULT '[]',
            expansion JSONB NOT NULL DEFAULT '{}',
            embedding vector(1536),  -- pgvector 向量类型，维度 1536（适配 sentence-transformers 模型输出）
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.create_index("idx_files_repository_id", "files", ["repository_id"])
    op.create_index("idx_files_content_hash", "files", ["content_hash"])
    op.create_index("idx_analysis_versions_repository_id", "analysis_versions", ["repository_id"])
    op.create_index("idx_knowledge_points_repository_id", "knowledge_points", ["repository_id"])
    op.create_index("idx_knowledge_points_category", "knowledge_points", ["category"])
    op.create_index("idx_knowledge_points_version", "knowledge_points", ["version"])
    # 创建 pgvector IVFFlat 索引（用于向量相似度搜索）
    # USING ivfflat: 使用倒排文件索引，适合大规模向量搜索
    # vector_cosine_ops: 使用余弦相似度度量
    # WITH (lists = 100): 索引列表数量，影响搜索精度和速度的平衡
    op.execute("CREATE INDEX idx_knowledge_points_embedding ON knowledge_points USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")


def downgrade() -> None:
    op.drop_index("idx_knowledge_points_embedding", table_name="knowledge_points")
    op.drop_index("idx_knowledge_points_version", table_name="knowledge_points")
    op.drop_index("idx_knowledge_points_category", table_name="knowledge_points")
    op.drop_index("idx_knowledge_points_repository_id", table_name="knowledge_points")
    op.drop_index("idx_analysis_versions_repository_id", table_name="analysis_versions")
    op.drop_index("idx_files_content_hash", table_name="files")
    op.drop_index("idx_files_repository_id", table_name="files")
    op.drop_table("knowledge_points")
    op.drop_table("analysis_versions")
    op.drop_table("files")
    op.drop_table("repositories")
    op.execute("DROP EXTENSION IF EXISTS vector")
