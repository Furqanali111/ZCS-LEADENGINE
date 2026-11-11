"""seed source_configs from docs/data-sources.md

Revision ID: 0002
Revises: 0001
"""
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# (key, name, status, access_method, rate_limit_per_sec, policy_reviewed_on, notes)
SOURCES = [
    ('npi_registry', 'CMS NPI Registry API', 'available', 'Free public JSON API, no key', 1, date(2026, 11, 11), 'Slice 1 backbone. Tested 2026-11-11. Published rate limit not confirmed, 1 request per second used.'),
    ('nppes_bulk', 'CMS NPPES bulk file', 'approved_not_built', 'Free public download', None, None, 'Deferred. Fallback if the API cap or missing provider counts become a real problem.'),
    ('practice_websites', 'Official practice websites', 'not_reviewed', 'Page fetch, per-site robots rules', None, None, 'Slice 3. Main route to websites, emails, and staff names.'),
    ('allbiz', 'Allbiz', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('yellow_pages', 'Yellow Pages', 'not_reviewed', None, None, None, 'First impression, unverified: Large U.S. coverage. Expect scraping restrictions.'),
    ('manta', 'Manta', 'not_reviewed', None, None, None, 'First impression, unverified: Small-business focus. Expect scraping restrictions.'),
    ('yelp', 'Yelp', 'not_reviewed', None, None, None, 'First impression, unverified: Has an official API with limits on storing its data. Review the API terms, not the website.'),
    ('chamber_of_commerce', 'Chamber of Commerce', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('hotfrog', 'Hotfrog', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('brownbook', 'Brownbook', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('cylexusa', 'CylexUSA', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('merchantcircle', 'MerchantCircle', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('superpages', 'Superpages', 'not_reviewed', None, None, None, 'First impression, unverified: Large U.S. coverage. Expect scraping restrictions.'),
    ('ezlocal', 'EZlocal', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('citysquares', 'CitySquares', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('local_com', 'Local.com', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('desknow', 'Desknow', 'not_reviewed', None, None, None, 'First impression, unverified: Unknown'),
    ('yellowbook', 'Yellowbook', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('showmelocal', 'ShowMeLocal', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('elocal', 'eLocal', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('opendi', 'Opendi', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('fyple', 'Fyple', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('n49', 'N49', 'not_reviewed', None, None, None, 'First impression, unverified: Believed to be Canada-focused. Likely out of scope.'),
    ('tupalo', 'Tupalo', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('infobel', 'Infobel', 'not_reviewed', None, None, None, 'First impression, unverified: Sells business data commercially. A paid license may be the permitted route.'),
    ('twofindlocal', '2FindLocal', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('ibegin', 'iBegin', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('callupcontact', 'Callupcontact', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('enrollbusiness', 'EnrollBusiness', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('yalwa', 'Yalwa', 'not_reviewed', None, None, None, 'First impression, unverified: Thin listing site'),
    ('yellowbot', 'YellowBot', 'not_reviewed', None, None, None, 'First impression, unverified: General listing site'),
    ('mapquest', 'MapQuest', 'not_reviewed', None, None, None, 'First impression, unverified: Has developer APIs. Review the API terms, not the website.'),
    ('better_business_bureau', 'Better Business Bureau', 'not_reviewed', None, None, None, 'First impression, unverified: Trusted profiles. Expect scraping restrictions.'),
]

source_configs = sa.table(
    "source_configs",
    sa.column("key", sa.Text),
    sa.column("name", sa.Text),
    sa.column("status", sa.Text),
    sa.column("access_method", sa.Text),
    sa.column("rate_limit_per_sec", sa.Float),
    sa.column("policy_reviewed_on", sa.Date),
    sa.column("notes", sa.Text),
)


def upgrade() -> None:
    cols = ("key", "name", "status", "access_method", "rate_limit_per_sec", "policy_reviewed_on", "notes")
    op.bulk_insert(source_configs, [dict(zip(cols, row)) for row in SOURCES])


def downgrade() -> None:
    op.execute(source_configs.delete().where(source_configs.c.key.in_([row[0] for row in SOURCES])))
