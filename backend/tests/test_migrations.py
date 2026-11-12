import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
from app.constants import ACTIVITY_TYPES, OUTCOMES, SUPPRESSION_KINDS
from app.db import Base

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def migrated_url(test_database_url):
    """A fresh, separate database so create_all/drop_all in the db fixture never clashes."""
    admin = create_engine(test_database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS migration_test"))
        c.execute(text("CREATE DATABASE migration_test"))
    url = make_url(test_database_url).set(database="migration_test").render_as_string(hide_password=False)
    yield url
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS migration_test WITH (FORCE)"))
    admin.dispose()


def alembic(url: str, *args: str) -> None:
    r = subprocess.run([sys.executable, "-m", "alembic", "-x", f"db_url={url}", *args], cwd=BACKEND, capture_output=True, text=True, env=os.environ)
    assert r.returncode == 0, r.stderr[-2000:]


def test_up_down_up_and_no_model_drift(migrated_url):
    alembic(migrated_url, "upgrade", "head")
    alembic(migrated_url, "downgrade", "base")
    alembic(migrated_url, "upgrade", "head")
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        drift = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert drift == []
        rows = dict(conn.execute(text("select key, status from source_configs")).all())
        npi = conn.execute(text("select rate_limit_per_sec, policy_reviewed_on::text from source_configs where key='npi_registry'")).one()
    engine.dispose()
    assert len(rows) == 36
    assert rows["npi_registry"] == "available" and rows["nppes_bulk"] == "approved_not_built"
    assert sum(s == "not_reviewed" for s in rows.values()) == 29
    assert tuple(npi) == (1.0, "2026-11-11")


RLS_SQL = text(
    "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "where c.relkind = 'r' and n.nspname = 'public'"
)


def test_rls_enabled_on_every_table_and_removed_on_downgrade(migrated_url):
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        rls = dict(conn.execute(RLS_SQL).all())
    assert len(rls) == 13 and all(rls.values()), rls
    alembic(migrated_url, "downgrade", "0002")
    with engine.connect() as conn:
        rls = dict(conn.execute(RLS_SQL).all())
    engine.dispose()
    assert len(rls) == 9 and not any(rls.values()), rls


def test_0004_adds_columns_and_rls(migrated_url):
    cols = text("select table_name, column_name from information_schema.columns where table_schema = 'public' "
                "and (table_name in ('lead_activities', 'suppression_list') or column_name in ('last_contacted_at', 'next_follow_up_at'))")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        rls = dict(conn.execute(RLS_SQL).all())
        found = {tuple(r) for r in conn.execute(cols).all()}
    assert rls["lead_activities"] and rls["suppression_list"]
    assert {("organizations", "last_contacted_at"), ("organizations", "next_follow_up_at"),
            ("lead_activities", "from_status"), ("suppression_list", "kind")} <= found
    alembic(migrated_url, "downgrade", "0003")
    with engine.connect() as conn:
        rls = dict(conn.execute(RLS_SQL).all())
        found = conn.execute(cols).all()
        fn = conn.execute(text("select count(*) from pg_proc where proname = 'lead_activities_append_only'")).scalar()
    engine.dispose()
    assert len(rls) == 9 and found == [] and fn == 0


def test_0004_trigger_is_append_only(migrated_url):
    alembic(migrated_url, "upgrade", "head")
    engine = create_engine(migrated_url)
    with engine.begin() as conn:
        oid = conn.execute(text("insert into organizations (npi, name, organization_type, state) values ('9', 'A', 'practice', 'TX') returning id")).scalar()
        conn.execute(text("insert into lead_activities (organization_id, type, summary) values (:o, 'note', 'hi')"), {"o": oid})
    for sql in ("update lead_activities set summary = 'x'", "delete from lead_activities"):
        with pytest.raises(Exception, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(sql))
    engine.dispose()
    alembic(migrated_url, "downgrade", "0003")


def test_0004_check_constraints_match_constants(migrated_url):
    alembic(migrated_url, "upgrade", "head")
    engine = create_engine(migrated_url)
    with engine.connect() as conn:
        defs = dict(conn.execute(text(
            "select conname, pg_get_constraintdef(oid) from pg_constraint where conname in "
            "('ck_lead_activities_type', 'ck_lead_activities_outcome', 'ck_suppression_list_kind')"
        )).all())
    engine.dispose()
    for name, values in (("ck_lead_activities_type", ACTIVITY_TYPES), ("ck_lead_activities_outcome", OUTCOMES), ("ck_suppression_list_kind", SUPPRESSION_KINDS)):
        assert set(re.findall(r"'([a-z_]+)'::text", defs[name])) == set(values), name


def test_0005_adds_enrichment_columns_and_source_rows(migrated_url):
    cols = text("select table_name, column_name from information_schema.columns where table_schema = 'public' and column_name in "
                "('website', 'website_evidence', 'enrichment_status', 'enriched_at', 'email', 'email_status', 'source_url', 'collected_at', 'enrich')")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        found = {tuple(r) for r in conn.execute(cols).all()}
        rows = dict(conn.execute(text("select key, status from source_configs where key in ('brave_search', 'practice_websites', 'yelp')")).all())
    assert {("organizations", "website"), ("organizations", "website_evidence"), ("organizations", "enrichment_status"),
            ("organizations", "enriched_at"), ("contacts", "email"), ("contacts", "email_status"), ("contacts", "source_url"),
            ("contacts", "collected_at"), ("search_jobs", "enrich")} <= found
    assert rows == {"brave_search": "approved_not_built", "practice_websites": "approved_not_built", "yelp": "rejected"}
    alembic(migrated_url, "downgrade", "0004")
    with engine.connect() as conn:
        found = conn.execute(cols).all()
        rows = dict(conn.execute(text("select key, status from source_configs where key in ('brave_search', 'practice_websites', 'yelp')")).all())
    engine.dispose()
    assert [r for r in found if r[0] == "organizations" and r[1] in ("website", "enrichment_status")] == []
    assert rows == {"practice_websites": "not_reviewed", "yelp": "not_reviewed"}


def test_0006_seeds_tavily_source(migrated_url):
    q = text("select status from source_configs where key = 'tavily_search'")
    ddg_q = text("select status from source_configs where key = 'duckduckgo_search'")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        assert conn.execute(q).scalar() == "approved_not_built"
        assert conn.execute(ddg_q).scalar() == "approved_not_built"
    alembic(migrated_url, "downgrade", "0005")
    with engine.connect() as conn:
        assert conn.execute(q).scalar() is None and conn.execute(ddg_q).scalar() is None
    engine.dispose()


def test_0007_indexes_exist_and_are_dropped_on_downgrade(migrated_url):
    names = ("ix_contacts_email_lower", "ix_organizations_phone_digits", "ix_organizations_fax_digits")
    q = text("select indexname from pg_indexes where schemaname = 'public' and indexname = any(:n)")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        assert {r[0] for r in conn.execute(q, {"n": list(names)})} == set(names)
    alembic(migrated_url, "downgrade", "0006")
    with engine.connect() as conn:
        assert conn.execute(q, {"n": list(names)}).all() == []
    engine.dispose()


def test_0008_outreach_templates_table(migrated_url):
    q = text("select c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
             "where n.nspname = 'public' and c.relname = 'outreach_templates'")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.connect() as conn:
        assert conn.execute(q).scalar() is True
    alembic(migrated_url, "downgrade", "0007")
    with engine.connect() as conn:
        assert conn.execute(q).first() is None
    engine.dispose()


def test_0009_search_progress_table_and_target_limit(migrated_url):
    q = text("select to_regclass('public.search_progress')")
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.begin() as conn:
        assert conn.execute(q).scalar() is not None
        conn.execute(text("insert into search_jobs (specialty, state, target_count, sources) values ('x', 'TX', 5000, '{npi_registry}')"))
    alembic(migrated_url, "downgrade", "0008")
    with engine.connect() as conn:
        assert conn.execute(q).scalar() is None
        assert conn.execute(text("select max(target_count) from search_jobs")).scalar() == 1200
    engine.dispose()


def test_0010_in_progress_status_allowed_and_downgrade_maps_it_back(migrated_url):
    engine = create_engine(migrated_url)
    alembic(migrated_url, "upgrade", "head")
    with engine.begin() as conn:
        conn.execute(text("insert into organizations (npi, name, organization_type, state, crm_status) values ('1', 'A', 'practice', 'TX', 'in_progress')"))
    alembic(migrated_url, "downgrade", "0009")
    with engine.connect() as conn:
        assert conn.execute(text("select crm_status from organizations")).scalar() == "researching"
    engine.dispose()
