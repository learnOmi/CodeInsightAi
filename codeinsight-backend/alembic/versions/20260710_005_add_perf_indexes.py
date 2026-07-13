"""Add performance indexes for ast_nodes, call_edges, module_dependencies

Revision ID: 20260710_005_add_perf_indexes
Revises: 20260709_004_add_files_unique_constraint
Create Date: 2026-07-10 00:00:00.000000

DB-1/DB-2 修复：为 ast_nodes、call_edges、module_dependencies 表添加缺失的索引。
- ast_nodes: (repository_id, node_type) 用于按类型查询，(repository_id, file_id) 用于按文件查询
- call_edges: (repository_id) 用于按仓库查询和删除
- module_dependencies: (repository_id) 用于按仓库查询和删除
"""

from alembic import op

revision = "20260710_005_add_perf_indexes"
down_revision = "20260709_004_add_files_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加性能索引"""
    # DB-1: ast_nodes 表索引
    op.create_index(
        "idx_ast_nodes_repo_type",
        "ast_nodes",
        ["repository_id", "node_type"],
    )
    op.create_index(
        "idx_ast_nodes_repo_file",
        "ast_nodes",
        ["repository_id", "file_id"],
    )

    # DB-2: call_edges 表索引
    op.create_index(
        "idx_call_edges_repository",
        "call_edges",
        ["repository_id"],
    )

    # DB-2: module_dependencies 表索引
    op.create_index(
        "idx_module_dependencies_repository",
        "module_dependencies",
        ["repository_id"],
    )


def downgrade() -> None:
    """移除性能索引"""
    op.drop_index("idx_module_dependencies_repository", table_name="module_dependencies")
    op.drop_index("idx_call_edges_repository", table_name="call_edges")
    op.drop_index("idx_ast_nodes_repo_file", table_name="ast_nodes")
    op.drop_index("idx_ast_nodes_repo_type", table_name="ast_nodes")
