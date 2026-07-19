"""
Sync embedding dimension to 1536 and change vector index to HNSW.

Changes:
1. Drop the old IVFFlat index on knowledge_points.embedding
2. Create a HNSW index for better query accuracy (matches ORM model definition)
   - HNSW provides higher recall than IVFFlat at comparable query speed for small-to-medium datasets
   - Uses cosine similarity (vector_cosine_ops) for embedding distance measurement
"""

from alembic import op

revision = "20260719_008_sync_embedding_dimension"
down_revision = "20260715_007_phase1_framework_enhancement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old IVFFlat index (created in 20260709_001_initial_schema)
    op.drop_index("idx_knowledge_points_embedding", table_name="knowledge_points", if_exists=True)

    # Create HNSW index for better query accuracy
    # HNSW (Hierarchical Navigable Small World) provides:
    # - Higher recall than IVFFlat (especially at low probe values)
    # - No training step required (unlike IVFFlat which needs clustering)
    # - Good performance for datasets up to millions of vectors
    op.execute(
        "CREATE INDEX idx_knowledge_points_embedding "
        "ON knowledge_points "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    # Drop the HNSW index
    op.drop_index("idx_knowledge_points_embedding", table_name="knowledge_points", if_exists=True)

    # Restore the original IVFFlat index
    op.execute(
        "CREATE INDEX idx_knowledge_points_embedding "
        "ON knowledge_points "
        "USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
