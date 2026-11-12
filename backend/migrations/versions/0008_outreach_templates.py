"""outreach templates: text the user copies by hand

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NOW = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "outreach_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), **NOW),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.CheckConstraint("kind IN ('call', 'email')", name="ck_outreach_templates_kind"),
    )
    op.execute("ALTER TABLE public.outreach_templates ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("outreach_templates")
