"""fix file_analysis_snapshots FK to avoid cascade deletion

Revision ID: 20260709_003_fix_snapshot_fk
Revises: 20260709_002_add_structure_tables
Create Date: 2026-07-13

P0 问题：file_analysis_snapshots.file_id → files.id 使用 ondelete=CASCADE。
_store_files_to_db 每次重建 files 表时会 DELETE+INSERT，导致所有历史快照
被级联删除，增量分析基准永久丢失。

修复：
- file_id FK: ondelete=CASCADE → ondelete=SET NULL
- file_id column: nullable=False → nullable=True
- 原复合唯一约束 (repo_id, version, file_id) 改为 partial unique index:
  仅 file_id IS NOT NULL 时唯一，避免 SET NULL 后多条 NULL 记录冲突
"""

import sqlalchemy as sa

from alembic import op

revision = "20260709_003_fix_snapshot_fk"
down_revision = "20260709_002_add_structure_tables"
branch_labels = None
depends_on = None

FK_NAME = "fk_file_analysis_snapshots_file_id_files"
UQ_NAME = "uq_snapshot_file_version"
PARTIAL_IDX_NAME = "uq_snapshot_repo_version_file_partial"
REPO_VERSION_IDX_NAME = "idx_snapshot_repo_version"


def upgrade() -> None:
    # 1. 删除原复合唯一约束
    op.drop_constraint(UQ_NAME, "file_analysis_snapshots", type_="unique", if_exists=True)

    # 2. 修改 file_id 外键：CASCADE → SET NULL
    op.drop_constraint(FK_NAME, "file_analysis_snapshots", type_="foreignkey", if_exists=True)
    op.create_foreign_key(
        FK_NAME,
        "file_analysis_snapshots",
        "files",
        ["file_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. 使 file_id 列可空
    op.alter_column("file_analysis_snapshots", "file_id", existing_type=sa.UUID(), nullable=True)

    # 4. 创建 partial unique index：仅 file_id IS NOT NULL 时唯一
    op.create_index(
        PARTIAL_IDX_NAME,
        "file_analysis_snapshots",
        ["repository_id", "analysis_version", "file_id"],
        unique=True,
        postgresql_where=sa.text("file_id IS NOT NULL"),
    )

    # 5. 添加 (repo_id, version) 索引用于增量分析查询
    op.create_index(
        REPO_VERSION_IDX_NAME,
        "file_analysis_snapshots",
        ["repository_id", "analysis_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(PARTIAL_IDX_NAME, table_name="file_analysis_snapshots", if_exists=True)
    op.drop_index(REPO_VERSION_IDX_NAME, table_name="file_analysis_snapshots", if_exists=True)

    op.alter_column("file_analysis_snapshots", "file_id", existing_type=sa.UUID(), nullable=False)

    op.drop_constraint(FK_NAME, "file_analysis_snapshots", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "file_analysis_snapshots",
        "files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_unique_constraint(
        UQ_NAME,
        "file_analysis_snapshots",
        ["repository_id", "analysis_version", "file_id"],
    )
