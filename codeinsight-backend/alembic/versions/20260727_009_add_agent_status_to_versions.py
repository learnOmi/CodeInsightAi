"""Add agent_status column to analysis_versions

Revision ID: 20260727_009_add_agent_status_to_versions
Revises: 20260719_008_sync_embedding_dimension
Create Date: 2026-07-27 00:00:00.000000

变更内容：
- analysis_versions 表新增 agent_status (TEXT) 列，用于记录每个 Agent 的执行状态
  支持部分重试场景。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260727_009_add_agent_status_to_versions"
down_revision = "20260719_008_sync_embedding_dimension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_versions",
        sa.Column("agent_status", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_versions", "agent_status")
