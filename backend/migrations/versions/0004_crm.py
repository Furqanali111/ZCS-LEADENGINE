"""crm: follow-up columns, append-only lead_activities, suppression_list

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ACTIVITY_TYPES = "'call', 'email', 'meeting', 'note', 'outcome', 'status_change'"
OUTCOMES = "'converted', 'interested', 'meeting_booked', 'no_answer', 'not_interested', 'other', 'spoke'"
SUPPRESSION_KINDS = "'email', 'npi', 'phone'"
PK = dict(server_default=sa.text("gen_random_uuid()"), nullable=False)
NOW = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("next_follow_up_at", sa.Date(), nullable=True))
    op.create_index("ix_organizations_next_follow_up_at", "organizations", ["next_follow_up_at"])

    op.create_table(
        "lead_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), **PK),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), **NOW),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), **NOW),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"type IN ({ACTIVITY_TYPES})", name="ck_lead_activities_type"),
        sa.CheckConstraint(f"outcome IS NULL OR outcome IN ({OUTCOMES})", name="ck_lead_activities_outcome"),
        sa.CheckConstraint("char_length(summary) <= 2000", name="ck_lead_activities_summary_length"),
        sa.CheckConstraint("type = 'status_change' OR summary IS NOT NULL", name="ck_lead_activities_summary_required"),
    )
    op.create_index("ix_lead_activities_org_occurred", "lead_activities", ["organization_id", sa.text("occurred_at DESC")])
    op.execute(
        "CREATE FUNCTION lead_activities_append_only() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'lead_activities is append-only'; END $$"
    )
    op.execute(
        "CREATE TRIGGER lead_activities_append_only BEFORE UPDATE OR DELETE ON lead_activities "
        "FOR EACH ROW EXECUTE FUNCTION lead_activities_append_only()"
    )

    op.create_table(
        "suppression_list",
        sa.Column("id", postgresql.UUID(as_uuid=True), **PK),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), **NOW),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "value", name="uq_suppression_list_kind_value"),
        sa.CheckConstraint(f"kind IN ({SUPPRESSION_KINDS})", name="ck_suppression_list_kind"),
    )
    for t in ("lead_activities", "suppression_list"):
        op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("suppression_list")
    op.drop_table("lead_activities")  # drops its trigger and index with it
    op.execute("DROP FUNCTION lead_activities_append_only()")
    op.drop_index("ix_organizations_next_follow_up_at", table_name="organizations")
    op.drop_column("organizations", "next_follow_up_at")
    op.drop_column("organizations", "last_contacted_at")
