"""email_sent flag on leads, tracked apart from the sales status

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("email_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("organizations", sa.Column("email_sent_by", sa.Text(), nullable=True))
    # leads already at Email sent, or with a logged email, count as sent
    op.execute("UPDATE organizations SET email_sent = true WHERE crm_status = 'email_sent' OR id IN (SELECT organization_id FROM lead_activities WHERE type = 'email')")


def downgrade() -> None:
    op.drop_column("organizations", "email_sent_by")
    op.drop_column("organizations", "email_sent")
