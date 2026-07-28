"""Stub: add agent_status to analysis_versions.

This migration was applied previously but the revision file was lost.
Recreating as a stub to restore the dependency chain so newer migrations
can be generated and applied cleanly.
"""

from alembic import op
from sqlalchemy import Column, String

import sqlalchemy as sa


revision = "20260727_009_add_agent_status_to_versions"
down_revision = "20260719_008_sync_embedding_dimension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The agent_status column may already exist; this is a no-op stub.
    # If the column doesn't exist, create it.
    op.add_column(
        "analysis_versions",
        Column("agent_status", sa.JSONB, nullable=True),
        postgresql_if_not_exists=True,
    )


def downgrade() -> None:
    pass
