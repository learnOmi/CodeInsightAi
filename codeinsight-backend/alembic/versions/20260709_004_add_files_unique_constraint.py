"""Add unique constraint on files table (repository_id, path)

Revision ID: 20260709_004_add_files_unique_constraint
Revises: 20260709_003_fix_snapshot_fk
Create Date: 2026-07-09 12:00:00.000000

修复：files 表缺少 (repository_id, path) 唯一约束。

模型定义中包含了 UniqueConstraint("repository_id", "path", name="uq_repository_file_path")，
但所有迁移脚本都没有创建这个约束，导致数据库层面无法保证同一仓库内文件路径的唯一性。
"""

from alembic import op

revision = "20260709_004_add_files_unique_constraint"
down_revision = "20260709_003_fix_snapshot_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_repository_file_path",
        "files",
        ["repository_id", "path"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_repository_file_path",
        "files",
        type_="unique",
    )
