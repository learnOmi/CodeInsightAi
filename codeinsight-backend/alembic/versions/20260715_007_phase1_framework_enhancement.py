"""Phase 1: 框架感知基础设施 — ast_nodes 扩展 + 新表

Revision ID: 20260715_007_phase1_framework_enhancement
Revises: 20260714_006_fix_repo_status_constraint
Create Date: 2026-07-15 00:00:00.000000

变更内容：
1. ast_nodes 表新增 tags (JSONB), annotations (JSONB), qualified_name (VARCHAR)
2. ast_nodes 新增 qualified_name 复合索引
3. 新建 external_dependencies 表
4. 新建 api_routes 表
5. 新建 framework_patterns 表
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "20260715_007_phase1_framework_enhancement"
down_revision = "20260714_006_fix_repo_status_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 Phase 1 基础设施迁移"""

    # ================================================================
    # 1. ast_nodes 表新增字段
    # ================================================================
    op.add_column(
        "ast_nodes",
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "ast_nodes",
        sa.Column("annotations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "ast_nodes",
        sa.Column("qualified_name", sa.String(1024), nullable=True),
    )

    # ================================================================
    # 2. ast_nodes 新增 qualified_name 复合索引
    # ================================================================
    op.create_index(
        "idx_ast_nodes_qualified_name",
        "ast_nodes",
        ["repository_id", "qualified_name"],
    )

    # ================================================================
    # 3. 新建 external_dependencies 表
    # ================================================================
    op.create_table(
        "external_dependencies",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repository_id", UUID, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "analysis_version_id",
            UUID,
            sa.ForeignKey("analysis_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ecosystem", sa.String(32), nullable=False),
        sa.Column("group_name", sa.String(256), nullable=True),
        sa.Column("artifact_name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("version_range", sa.String(64), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False, server_default=sa.text("'compile'")),
        sa.Column("declaration_file", sa.String(1024), nullable=True),
        sa.Column("used_by_files", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_external_deps_repo", "external_dependencies", ["repository_id"])
    op.create_index("idx_external_deps_version", "external_dependencies", ["analysis_version_id"])
    op.create_index("idx_external_deps_ecosystem", "external_dependencies", ["repository_id", "ecosystem"])

    # ================================================================
    # 4. 新建 api_routes 表
    # ================================================================
    op.create_table(
        "api_routes",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repository_id", UUID, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "analysis_version_id",
            UUID,
            sa.ForeignKey("analysis_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ast_node_id",
            UUID,
            sa.ForeignKey("ast_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("http_method", sa.String(8), nullable=False),
        sa.Column("path_pattern", sa.String(1024), nullable=False),
        sa.Column("handler_function", sa.String(256), nullable=False),
        sa.Column("handler_file", sa.String(1024), nullable=False),
        sa.Column("middlewares", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("framework", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_api_routes_repo", "api_routes", ["repository_id"])
    op.create_index("idx_api_routes_version", "api_routes", ["analysis_version_id"])
    op.create_index("idx_api_routes_method_path", "api_routes", ["repository_id", "http_method", "path_pattern"])

    # ================================================================
    # 5. 新建 framework_patterns 表
    # ================================================================
    op.create_table(
        "framework_patterns",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repository_id", UUID, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "analysis_version_id",
            UUID,
            sa.ForeignKey("analysis_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("framework", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_framework_patterns_repo", "framework_patterns", ["repository_id"])
    op.create_index("idx_framework_patterns_version", "framework_patterns", ["analysis_version_id"])
    op.create_index(
        "idx_framework_patterns_repo_fw_ver",
        "framework_patterns",
        ["repository_id", "framework", "analysis_version_id"],
        unique=True,
    )


def downgrade() -> None:
    """回滚 Phase 1 基础设施迁移"""

    # 5. 删除 framework_patterns 表
    op.drop_index("idx_framework_patterns_repo_fw_ver", table_name="framework_patterns")
    op.drop_index("idx_framework_patterns_version", table_name="framework_patterns")
    op.drop_index("idx_framework_patterns_repo", table_name="framework_patterns")
    op.drop_table("framework_patterns")

    # 4. 删除 api_routes 表
    op.drop_index("idx_api_routes_method_path", table_name="api_routes")
    op.drop_index("idx_api_routes_version", table_name="api_routes")
    op.drop_index("idx_api_routes_repo", table_name="api_routes")
    op.drop_table("api_routes")

    # 3. 删除 external_dependencies 表
    op.drop_index("idx_external_deps_ecosystem", table_name="external_dependencies")
    op.drop_index("idx_external_deps_version", table_name="external_dependencies")
    op.drop_index("idx_external_deps_repo", table_name="external_dependencies")
    op.drop_table("external_dependencies")

    # 2. 删除 ast_nodes 索引
    op.drop_index("idx_ast_nodes_qualified_name", table_name="ast_nodes")

    # 1. 删除 ast_nodes 新增字段
    op.drop_column("ast_nodes", "qualified_name")
    op.drop_column("ast_nodes", "annotations")
    op.drop_column("ast_nodes", "tags")
