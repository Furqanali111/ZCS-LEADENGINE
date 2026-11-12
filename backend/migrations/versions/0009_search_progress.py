"""search progress cursor and a higher target count

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

NOW = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "search_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), server_default="", nullable=False),
        sa.Column("include_subparts", sa.Boolean(), nullable=False),
        sa.Column("include_hospitals", sa.Boolean(), nullable=False),
        sa.Column("cursor", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("leads_fetched", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), **NOW),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("specialty", "state", "city", "include_subparts", "include_hospitals", name="uq_search_progress_key"),
    )
    op.execute("ALTER TABLE public.search_progress ENABLE ROW LEVEL SECURITY")
    op.drop_constraint("ck_search_jobs_target_count", "search_jobs")
    op.create_check_constraint("ck_search_jobs_target_count", "search_jobs", "target_count BETWEEN 1 AND 50000")


def downgrade() -> None:
    op.execute("UPDATE search_jobs SET target_count = 1200 WHERE target_count > 1200")
    op.drop_constraint("ck_search_jobs_target_count", "search_jobs")
    op.create_check_constraint("ck_search_jobs_target_count", "search_jobs", "target_count BETWEEN 1 AND 1200")
    op.drop_table("search_progress")
