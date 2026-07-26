"""Change agent_status column from Text to JSON

Revision ID: 20260727_010_change_agent_status_to_json
Revises: 20260727_009_add_agent_status_to_versions
Create Date: 2026-07-27 00:00:00.000000

变更内容：
- analysis_versions 表的 agent_status 列从 TEXT 改为 JSON（PostgreSQL JSON 类型）
  修复 TypeError: expected str, got dict 错误，支持直接存储 agent 状态字典。
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260727_010_change_agent_status_to_json"
down_revision = "20260727_009_add_agent_status_to_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "analysis_versions",
        "agent_status",
        type_=postgresql.JSON(),
        existing_type=sa.Text(),
        nullable=True,
        postgresql_using="agent_status::json",
    )


def downgrade() -> None:
    op.alter_column(
        "analysis_versions",
        "agent_status",
        type_=sa.Text(),
        existing_type=postgresql.JSON(),
        nullable=True,
    )
