"""add current_task_id to repositories

Revision ID: 20260728_011_add_current_task_id_to_repositories
Revises: 20260728_010_rr1_rr3_rr4_version_isolation_progress
Create Date: 2026-07-28 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260728_011_add_current_task_id_to_repositories"
down_revision: Union[str, None] = "20260728_010_rr1_rr3_rr4_version_isolation_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("current_task_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repositories", "current_task_id")
