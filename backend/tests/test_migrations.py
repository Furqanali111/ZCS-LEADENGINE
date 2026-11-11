import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
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
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        rows = dict(conn.execute(text("select key, status from source_configs")).all())
        npi = conn.execute(text("select rate_limit_per_sec, policy_reviewed_on::text from source_configs where key='npi_registry'")).one()
    engine.dispose()
    assert len(rows) == 33
    assert rows["npi_registry"] == "available" and rows["nppes_bulk"] == "approved_not_built"
    assert sum(s == "not_reviewed" for s in rows.values()) == 31
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
    assert len(rls) == 9 and all(rls.values()), rls
    alembic(migrated_url, "downgrade", "0002")
    with engine.connect() as conn:
        rls = dict(conn.execute(RLS_SQL).all())
    engine.dispose()
    assert len(rls) == 9 and not any(rls.values()), rls
