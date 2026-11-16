"""search_jobs.host: the computer whose worker runs the job (null: any worker may take it)

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_jobs", sa.Column("host", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_jobs", "host")
