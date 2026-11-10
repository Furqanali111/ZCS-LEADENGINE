"""enable row level security on all tables (no policies: deny API roles)

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = [
    "alembic_version", "organizations", "search_jobs", "source_configs", "contacts",
    "lead_scores", "locations", "search_job_leads", "source_records",
]


def upgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE public.{t} DISABLE ROW LEVEL SECURITY")
