"""organization_phones table, opening hours and maps status on organizations, google_maps source

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

MAPS_STATUSES = "'failed', 'matched', 'no_match', 'not_run'"


def upgrade() -> None:
    op.create_table(
        "organization_phones",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("differs_from_npi", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "source_key", "phone", name="uq_organization_phones_org_source_phone"),
    )
    op.create_index("ix_organization_phones_organization_id", "organization_phones", ["organization_id"])
    op.execute("ALTER TABLE public.organization_phones ENABLE ROW LEVEL SECURITY")
    op.add_column("organizations", sa.Column("hours", postgresql.JSONB(), nullable=True))
    op.add_column("organizations", sa.Column("maps_status", sa.Text(), server_default="not_run", nullable=False))
    op.add_column("organizations", sa.Column("maps_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("maps_url", sa.Text(), nullable=True))
    op.create_check_constraint("ck_organizations_maps_status", "organizations", f"maps_status IN ({MAPS_STATUSES})")
    op.execute(
        "INSERT INTO source_configs (key, name, status, access_method, rate_limit_per_sec, policy_reviewed_on, notes) VALUES "
        "('google_maps', 'Google Maps (View Map link from the NPI address)', 'available', "
        "'Headless browser on the public Maps page', 0.2, '2026-11-14', "
        "'Owner-accepted risk 2026-11-14: Google terms forbid scraping and storing this content. Hospitals only, one lead at a time, stops on a CAPTCHA or block, never bypassed.')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_configs WHERE key = 'google_maps'")
    op.drop_constraint("ck_organizations_maps_status", "organizations")
    op.drop_column("organizations", "maps_url")
    op.drop_column("organizations", "maps_checked_at")
    op.drop_column("organizations", "maps_status")
    op.drop_column("organizations", "hours")
    op.drop_index("ix_organization_phones_organization_id", "organization_phones")
    op.drop_table("organization_phones")
