"""add the called_no_answer sales status (called, nobody picked up)

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

OLD = ("called", "converted", "do_not_contact", "email_sent", "follow_up_required", "in_progress", "interested", "meeting_scheduled", "new", "not_interested", "researching")


def _swap(values: tuple[str, ...]) -> None:
    op.drop_constraint("ck_organizations_crm_status", "organizations", type_="check")
    op.create_check_constraint("ck_organizations_crm_status", "organizations", "crm_status IN (" + ", ".join(f"'{v}'" for v in sorted(values)) + ")")


def upgrade() -> None:
    _swap(OLD + ("called_no_answer",))


def downgrade() -> None:
    op.execute("UPDATE organizations SET crm_status = 'called' WHERE crm_status = 'called_no_answer'")
    _swap(OLD)
