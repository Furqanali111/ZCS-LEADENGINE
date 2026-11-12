"""add the in_progress sales status (claimed by a salesperson)

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

OLD = ("called", "converted", "do_not_contact", "email_sent", "follow_up_required", "interested", "meeting_scheduled", "new", "not_interested", "researching")


def _swap(values: tuple[str, ...]) -> None:
    op.drop_constraint("ck_organizations_crm_status", "organizations", type_="check")
    op.create_check_constraint("ck_organizations_crm_status", "organizations", "crm_status IN (" + ", ".join(f"'{v}'" for v in sorted(values)) + ")")


def upgrade() -> None:
    _swap(OLD + ("in_progress",))


def downgrade() -> None:
    op.execute("UPDATE organizations SET crm_status = 'researching' WHERE crm_status = 'in_progress'")
    _swap(OLD)
