"""organization_phones.listing_address: where the Maps listing is when it differs from the NPI address

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_phones", sa.Column("listing_address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organization_phones", "listing_address")
