"""trigram, lower(email) and phone digit indexes

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
    # pg_trgm ships with Supabase; the embedded test Postgres lacks it, so the trigram indexes are skipped there
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm') THEN
                CREATE EXTENSION IF NOT EXISTS pg_trgm;
                CREATE INDEX ix_organizations_name_trgm ON organizations USING gin (lower(name) gin_trgm_ops);
                CREATE INDEX ix_organizations_city_trgm ON organizations USING gin (lower(city) gin_trgm_ops);
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX ix_contacts_email_lower ON contacts (lower(email))")
    op.execute(f"CREATE INDEX ix_organizations_phone_digits ON organizations ({_digits('phone')})")
    op.execute(f"CREATE INDEX ix_organizations_fax_digits ON organizations ({_digits('fax')})")


def downgrade() -> None:
    for name in ("ix_organizations_fax_digits", "ix_organizations_phone_digits", "ix_contacts_email_lower",
                 "ix_organizations_city_trgm", "ix_organizations_name_trgm"):
        op.execute(f"DROP INDEX IF EXISTS {name}")  # pg_trgm stays installed
