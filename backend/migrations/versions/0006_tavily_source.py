"""seed the Tavily search source

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO source_configs (key, name, status, access_method, policy_reviewed_on, notes) VALUES "
        "('tavily_search', 'Tavily Search API', 'approved_not_built', 'Official search API, key in backend .env', '2026-11-12', "
        "'Results used in memory only, never stored. Internal business use allowed by its terms.')"
    )
    op.execute(
        "INSERT INTO source_configs (key, name, status, access_method, notes) VALUES "
        "('duckduckgo_search', 'DuckDuckGo search (ddgs fallback)', 'approved_not_built', 'Unofficial ddgs library, no key', "
        "'No official API. Used only after Tavily credits run out. Owner accepted the acceptable use policy risk on 2026-11-12.')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM source_configs WHERE key IN ('tavily_search', 'duckduckgo_search')")
