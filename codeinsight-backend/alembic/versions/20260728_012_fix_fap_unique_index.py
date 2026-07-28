"""
Fix file_analysis_progress index: replace non-unique idx with partial unique index.

The original migration 20260728_010 created a regular (non-unique) index
`idx_fap_version_file_stage` on (analysis_version_id, file_path, stage).
However, the DAO's UPSERT uses ON CONFLICT DO UPDATE which requires a
unique constraint/index. This migration replaces the non-unique index
with a partial unique index `uq_fap_version_file_stage` that matches
the model definition.

Changes:
  - Drop idx_fap_version_file_stage (non-unique)
  - Create uq_fap_version_file_stage (partial unique, analysis_version_id IS NOT NULL)
"""

from alembic import op

revision = "20260728_012_fix_fap_unique_index"
down_revision = "20260728_011_add_current_task_id_to_repositories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old non-unique index
    op.drop_index(
        "idx_fap_version_file_stage",
        table_name="file_analysis_progress",
        if_exists=True,
    )
    # Create the partial unique index (matches model __table_args__)
    op.create_index(
        "uq_fap_version_file_stage",
        "file_analysis_progress",
        ["analysis_version_id", "file_path", "stage"],
        unique=True,
        postgresql_where="analysis_version_id IS NOT NULL",
    )


def downgrade() -> None:
    # Drop the partial unique index
    op.drop_index(
        "uq_fap_version_file_stage",
        table_name="file_analysis_progress",
        if_exists=True,
    )
    # Restore the old non-unique index
    op.create_index(
        "idx_fap_version_file_stage",
        "file_analysis_progress",
        ["analysis_version_id", "file_path", "stage"],
    )