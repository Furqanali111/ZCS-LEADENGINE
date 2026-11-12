"""saved searches: a salesperson's reusable search form values

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

NOW = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("include_practices", sa.Boolean(), nullable=False),
        sa.Column("include_solo", sa.Boolean(), nullable=False),
        sa.Column("include_subparts", sa.Boolean(), nullable=False),
        sa.Column("include_hospitals", sa.Boolean(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("enrich", sa.Boolean(), nullable=False),
        sa.Column("sources", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), **NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), **NOW),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_saved_searches_name_len"),
        sa.CheckConstraint("target_count BETWEEN 1 AND 50000", name="ck_saved_searches_target_count"),
    )
    op.create_index("uq_saved_searches_name_lower", "saved_searches", [sa.text("lower(name)")], unique=True)
    op.execute("ALTER TABLE public.saved_searches ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("saved_searches")
