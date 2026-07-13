"""Update repository status CHECK constraint to match RepositoryStatus enum

Revision ID: 20260714_006_fix_repo_status_constraint
Revises: 20260710_005_add_perf_indexes
Create Date: 2026-07-14 00:00:00.000000

M-3 修复：原 CHECK 约束包含 analyzing_structures（TaskStatus 的细分状态，不应在此），
缺失 cancelled（实际使用中会被设置）。更新约束使其与 RepositoryStatus StrEnum 一致。
"""

from alembic import op

revision = "20260714_006_fix_repo_status_constraint"
down_revision = "20260710_005_add_perf_indexes"
branch_labels = None
depends_on = None

VALID_STATUSES = ("pending", "analyzing", "completed", "failed", "cancelled")


def upgrade() -> None:
    """更新 repository 表 status 列的 CHECK 约束"""
    op.drop_constraint("chk_repository_status", "repositories", type_="check")
    op.create_check_constraint(
        "chk_repository_status",
        "repositories",
        f"status IN ({', '.join(f"'{s}'" for s in VALID_STATUSES)})",
    )


def downgrade() -> None:
    """恢复原始 CHECK 约束"""
    op.drop_constraint("chk_repository_status", "repositories", type_="check")
    op.create_check_constraint(
        "chk_repository_status",
        "repositories",
        "status IN ('pending', 'analyzing', 'analyzing_structures', 'completed', 'failed')",
    )
