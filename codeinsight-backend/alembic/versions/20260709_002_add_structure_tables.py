"""add ast_nodes call_edges module_dependencies file_analysis_snapshots

Revision ID: 20260709_002_add_structure_tables
Revises: 20260709_001_initial_schema
Create Date: 2026-07-09 12:00:00.000000

新增以下表：
- ast_nodes: AST 节点表，存储代码结构（函数、类、方法等）
- call_edges: 调用边表，存储函数调用关系
- module_dependencies: 模块依赖表，存储模块间依赖关系
- file_analysis_snapshots: 文件分析快照表，用于增量分析
"""

import sqlalchemy as sa

from alembic import op

revision = "20260709_002_add_structure_tables"
down_revision = "20260709_001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 ast_nodes 表
    op.create_table(
        "ast_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("node_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_column", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parent_node_id", sa.UUID(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_node_id"], ["ast_nodes.id"], ondelete="CASCADE"),
    )

    # 创建 call_edges 表
    op.create_table(
        "call_edges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("caller_node_id", sa.UUID(), nullable=False),
        sa.Column("callee_node_id", sa.UUID(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), nullable=False),
        sa.Column("call_name", sa.String(), nullable=False),
        sa.Column("call_type", sa.String(), nullable=False, server_default="static"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["caller_node_id"], ["ast_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["callee_node_id"], ["ast_nodes.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "call_type IN ('static', 'dynamic', 'unknown')",
            name="chk_call_type",
        ),
    )

    # 创建 module_dependencies 表
    op.create_table(
        "module_dependencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("importer_file_id", sa.UUID(), nullable=False),
        sa.Column("imported_file_id", sa.UUID(), nullable=True),
        sa.Column("import_name", sa.String(), nullable=False),
        sa.Column("import_type", sa.String(), nullable=False, server_default="absolute"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["importer_file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_file_id"], ["files.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "import_type IN ('relative', 'absolute', 'external')",
            name="chk_import_type",
        ),
    )

    # 创建 file_analysis_snapshots 表
    op.create_table(
        "file_analysis_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_id", sa.UUID(), nullable=False),
        sa.Column("analysis_version", sa.String(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("nodes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edges_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deps_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "content_hash IS NOT NULL AND length(content_hash) > 0",
            name="chk_snapshot_content_hash",
        ),
    )

    # 创建索引
    # ast_nodes 索引
    op.create_index("idx_ast_nodes_repository_id", "ast_nodes", ["repository_id"])
    op.create_index("idx_ast_nodes_file_id", "ast_nodes", ["file_id"])
    op.create_index("idx_ast_nodes_parent_node_id", "ast_nodes", ["parent_node_id"])
    op.create_index("idx_ast_nodes_node_type", "ast_nodes", ["node_type"])
    op.create_index("idx_ast_nodes_file_path", "ast_nodes", ["file_path"])

    # call_edges 索引
    op.create_index("idx_call_edges_repository_id", "call_edges", ["repository_id"])
    op.create_index("idx_call_edges_caller_node_id", "call_edges", ["caller_node_id"])
    op.create_index("idx_call_edges_callee_node_id", "call_edges", ["callee_node_id"])

    # module_dependencies 索引
    op.create_index("idx_module_deps_repository_id", "module_dependencies", ["repository_id"])
    op.create_index("idx_module_deps_importer_file_id", "module_dependencies", ["importer_file_id"])
    op.create_index("idx_module_deps_imported_file_id", "module_dependencies", ["imported_file_id"])

    # file_analysis_snapshots 索引
    op.create_index("idx_snapshot_repo_version", "file_analysis_snapshots", ["repository_id", "analysis_version"])
    op.create_index("idx_snapshot_repo_file", "file_analysis_snapshots", ["repository_id", "file_id"])
    op.create_index("idx_snapshot_content_hash", "file_analysis_snapshots", ["content_hash"])


def downgrade() -> None:
    # 删除索引
    op.drop_index("idx_snapshot_content_hash", table_name="file_analysis_snapshots")
    op.drop_index("idx_snapshot_repo_file", table_name="file_analysis_snapshots")
    op.drop_index("idx_snapshot_repo_version", table_name="file_analysis_snapshots")
    op.drop_index("idx_module_deps_importer_file_id", table_name="module_dependencies")
    op.drop_index("idx_module_deps_repository_id", table_name="module_dependencies")
    op.drop_index("idx_call_edges_callee_node_id", table_name="call_edges")
    op.drop_index("idx_call_edges_caller_node_id", table_name="call_edges")
    op.drop_index("idx_call_edges_repository_id", table_name="call_edges")
    op.drop_index("idx_ast_nodes_file_path", table_name="ast_nodes")
    op.drop_index("idx_ast_nodes_node_type", table_name="ast_nodes")
    op.drop_index("idx_ast_nodes_parent_node_id", table_name="ast_nodes")
    op.drop_index("idx_ast_nodes_file_id", table_name="ast_nodes")
    op.drop_index("idx_ast_nodes_repository_id", table_name="ast_nodes")

    # 删除表
    op.drop_table("file_analysis_snapshots")
    op.drop_table("module_dependencies")
    op.drop_table("call_edges")
    op.drop_table("ast_nodes")
