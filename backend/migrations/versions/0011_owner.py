"""lead owner (who is working it) and activity actor

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("owner", sa.Text(), nullable=True))
    op.add_column("lead_activities", sa.Column("actor", sa.Text(), nullable=True))
    op.create_index("ix_organizations_owner", "organizations", ["owner"])


def downgrade() -> None:
    op.drop_index("ix_organizations_owner", table_name="organizations")
    op.drop_column("lead_activities", "actor")
    op.drop_column("organizations", "owner")
