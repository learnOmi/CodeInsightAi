"""Alembic migration script template."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "{{ revision }}"
down_revision = "{{ down_revision }}"
branch_labels = "{{ branch_labels }}"
depends_on = "{{ depends_on }}"


def upgrade() -> None:
    """Upgrade database schema."""
    {{ upgrade_ops }}


def downgrade() -> None:
    """Downgrade database schema."""
    {{ downgrade_ops }}
