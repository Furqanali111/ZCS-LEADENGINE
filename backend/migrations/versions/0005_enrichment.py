"""enrichment: website and email columns, widened contact roles, source records

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ENRICHMENT_STATUSES = "'enriched', 'failed', 'no_website_found', 'not_run', 'rejected_by_user'"
OLD_ROLES = "'authorized_official', 'provider'"
NEW_ROLES = "'authorized_official', 'general', 'provider', 'staff'"


def upgrade() -> None:
    op.add_column("organizations", sa.Column("website", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("website_evidence", postgresql.JSONB(), nullable=True))
    op.add_column("organizations", sa.Column("enrichment_status", sa.Text(), server_default="not_run", nullable=False))
    op.add_column("organizations", sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_organizations_enrichment_status", "organizations", f"enrichment_status IN ({ENRICHMENT_STATUSES})")

    op.add_column("contacts", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("contacts", sa.Column("email_status", sa.Text(), nullable=True))
    op.add_column("contacts", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("contacts", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_contacts_email_status", "contacts", "email_status IS NULL OR email_status IN ('found_on_page')")
    op.drop_constraint("ck_contacts_role", "contacts")
    op.create_check_constraint("ck_contacts_role", "contacts", f"role IN ({NEW_ROLES})")

    op.add_column("search_jobs", sa.Column("enrich", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    op.execute(
        "INSERT INTO source_configs (key, name, status, access_method, policy_reviewed_on, notes) VALUES "
        "('brave_search', 'Brave Search API', 'approved_not_built', 'Official search API, key in backend .env', '2026-11-12', "
        "'Results used in memory only, never stored. Storage terms need owner confirmation before the live run.')"
    )
    op.execute(
        "UPDATE source_configs SET status = 'approved_not_built', policy_reviewed_on = '2026-11-12', rate_limit_per_sec = 1, "
        "notes = 'Public pages of the practice itself. Fetched with a descriptive user agent, robots.txt honored including Crawl-delay, "
        "about 1 request per second per domain, no logins, no CAPTCHA or anti-bot bypass.' WHERE key = 'practice_websites'"
    )
    op.execute(
        "UPDATE source_configs SET status = 'rejected', policy_reviewed_on = '2026-11-12', "
        "notes = 'API terms (reviewed 2026-11-12) forbid storing content beyond 24 hours, scraping, building a database, and commercial use.' "
        "WHERE key = 'yelp'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_configs WHERE key = 'brave_search'")
    op.execute(
        "UPDATE source_configs SET status = 'not_reviewed', policy_reviewed_on = NULL, rate_limit_per_sec = NULL, "
        "notes = 'Slice 3. Main route to websites, emails, and staff names.' WHERE key = 'practice_websites'"
    )
    op.execute(
        "UPDATE source_configs SET status = 'not_reviewed', policy_reviewed_on = NULL, "
        "notes = 'First impression, unverified: Has an official API with limits on storing its data. Review the API terms, not the website.' "
        "WHERE key = 'yelp'"
    )
    op.drop_column("search_jobs", "enrich")
    op.execute("DELETE FROM contacts WHERE role IN ('staff', 'general')")
    op.drop_constraint("ck_contacts_role", "contacts")
    op.create_check_constraint("ck_contacts_role", "contacts", f"role IN ({OLD_ROLES})")
    op.drop_constraint("ck_contacts_email_status", "contacts")
    for c in ("collected_at", "source_url", "email_status", "email"):
        op.drop_column("contacts", c)
    op.drop_constraint("ck_organizations_enrichment_status", "organizations")
    for c in ("enriched_at", "enrichment_status", "website_evidence", "website"):
        op.drop_column("organizations", c)
