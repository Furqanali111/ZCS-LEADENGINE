"""outreach templates: allow the message kind

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_outreach_templates_kind", "outreach_templates")
    op.create_check_constraint("ck_outreach_templates_kind", "outreach_templates", "kind IN ('call', 'email', 'message')")


def downgrade() -> None:
    op.execute("DELETE FROM outreach_templates WHERE kind = 'message'")
    op.drop_constraint("ck_outreach_templates_kind", "outreach_templates")
    op.create_check_constraint("ck_outreach_templates_kind", "outreach_templates", "kind IN ('call', 'email')")
