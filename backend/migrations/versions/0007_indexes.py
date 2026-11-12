"""lower(email) and phone digit indexes

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _digits(col: str) -> str:
    return rf"regexp_replace(regexp_replace({col}, '\D', '', 'g'), '^1(?=\d{{10}}$)', '')"


def upgrade() -> None:
    op.execute("CREATE INDEX ix_contacts_email_lower ON contacts (lower(email))")
    op.execute(f"CREATE INDEX ix_organizations_phone_digits ON organizations ({_digits('phone')})")
    op.execute(f"CREATE INDEX ix_organizations_fax_digits ON organizations ({_digits('fax')})")


def downgrade() -> None:
    for name in ("ix_organizations_fax_digits", "ix_organizations_phone_digits", "ix_contacts_email_lower"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
