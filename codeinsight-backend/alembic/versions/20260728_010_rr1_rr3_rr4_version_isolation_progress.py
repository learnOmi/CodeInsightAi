"""
R-R1/R-R3/R-R4: Add version isolation and progress tracking.

Changes:
R-R1:  version-id isolated cleanup
  - ast_nodes.analysis_version_id (nullable UUID)
  - call_edges.analysis_version_id (nullable UUID)
  - module_dependencies.analysis_version_id (nullable UUID)

R-R3:  Milestone snapshots
  - file_analysis_snapshots.stage (VARCHAR(32), default 'storing')
  - Replace old snapshot indexes with stage-aware versions

R-R4:  File-level progress tracking
  - New table: file_analysis_progress

Other (already in model definitions, syncing to schema):
  - analysis_versions.scan_metadata (JSONB, nullable)
  - analysis_versions.stages_completed (JSONB, nullable)
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260728_010_rr1_rr3_rr4_version_isolation_progress"
down_revision = "20260727_009_add_agent_status_to_versions"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ---- R-R3: file_analysis_snapshots.stage ----
    op.add_column(
        "file_analysis_snapshots",
        sa.Column("stage", sa.String(32), nullable=False, server_default="storing"),
    )

    # Drop old snapshot indexes (will be replaced with stage-aware versions)
    op.drop_index("idx_snapshot_repo_file", table_name="file_analysis_snapshots", if_exists=True)
    op.drop_index("idx_snapshot_repo_version", table_name="file_analysis_snapshots", if_exists=True)

    # Recreate indexes with stage
    op.create_index(
        "idx_snapshot_repo_version_stage",
        "file_analysis_snapshots",
        ["repository_id", "analysis_version", "stage"],
    )
    op.create_index(
        "idx_snapshot_content_hash",
        "file_analysis_snapshots",
        ["content_hash"],
    )

    # ---- R-R1: analysis_version_id on structured data tables ----
    op.add_column(
        "ast_nodes",
        sa.Column("analysis_version_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ast_nodes_analysis_version",
        "ast_nodes", "analysis_versions",
        ["analysis_version_id"], ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "call_edges",
        sa.Column("analysis_version_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_call_edges_analysis_version",
        "call_edges", "analysis_versions",
        ["analysis_version_id"], ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "module_dependencies",
        sa.Column("analysis_version_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_module_deps_analysis_version",
        "module_dependencies", "analysis_versions",
        ["analysis_version_id"], ["id"],
        ondelete="CASCADE",
    )

    # ---- R-R4: New table file_analysis_progress ----
    op.create_table(
        "file_analysis_progress",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_version_id", sa.Uuid(), nullable=True),
        sa.Column("file_id", sa.Uuid(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False,
                  server_default="ast"),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="pending"),
        sa.Column("progress_data", postgresql.JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_version_id"], ["analysis_versions.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"],
                                ondelete="SET NULL"),
        sa.CheckConstraint(
            "stage IN ('scan','ast','structures','frameworks','ai','storing')",
            name="chk_fap_stage",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed','skipped')",
            name="chk_fap_status",
        ),
    )

    op.create_index(
        "idx_fap_version_file_stage",
        "file_analysis_progress",
        ["analysis_version_id", "file_path", "stage"],
    )
    op.create_index(
        "idx_fap_version_stage_status",
        "file_analysis_progress",
        ["analysis_version_id", "stage", "status"],
    )
    op.create_index(
        "idx_fap_repo_stage_status",
        "file_analysis_progress",
        ["repository_id", "stage", "status"],
    )

    # ---- scan_metadata / stages_completed on analysis_versions ----
    op.add_column(
        "analysis_versions",
        sa.Column("scan_metadata", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "analysis_versions",
        sa.Column("stages_completed", postgresql.JSONB, nullable=True),
    )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop new columns from analysis_versions
    op.drop_column("analysis_versions", "stages_completed")
    op.drop_column("analysis_versions", "scan_metadata")

    # Drop R-R4 table
    op.drop_table("file_analysis_progress")

    # Drop R-R1 columns and FKs
    op.drop_constraint(
        "fk_module_deps_analysis_version", "module_dependencies", type_="foreignkey",
    )
    op.drop_column("module_dependencies", "analysis_version_id")

    op.drop_constraint(
        "fk_call_edges_analysis_version", "call_edges", type_="foreignkey",
    )
    op.drop_column("call_edges", "analysis_version_id")

    op.drop_constraint(
        "fk_ast_nodes_analysis_version", "ast_nodes", type_="foreignkey",
    )
    op.drop_column("ast_nodes", "analysis_version_id")

    # Drop R-R3 stage column and indexes
    op.drop_index("idx_snapshot_content_hash", table_name="file_analysis_snapshots")
    op.drop_index("idx_snapshot_repo_version_stage", table_name="file_analysis_snapshots")
    op.drop_column("file_analysis_snapshots", "stage")

    # Restore old snapshot indexes
    op.create_index(
        "idx_snapshot_repo_version",
        "file_analysis_snapshots",
        ["repository_id", "analysis_version"],
    )
    op.create_index(
        "idx_snapshot_repo_file",
        "file_analysis_snapshots",
        ["repository_id", "file_id"],
    )
