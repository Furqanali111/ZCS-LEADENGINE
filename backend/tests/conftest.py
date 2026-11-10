import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import Base, get_session
from app.main import create_app


def same_database(a: str, b: str) -> bool:
    """Compare host, port, database and user, ignoring driver and query."""
    x, y = make_url(a), make_url(b)
    return (x.host, x.port or 5432, x.database, x.username) == (y.host, y.port or 5432, y.database, y.username)


@pytest.fixture(scope="session")
def test_database_url():
    url = get_settings().test_database_url
    if url:
        yield url
        return
    import pgserver

    with tempfile.TemporaryDirectory() as d:
        server = pgserver.get_server(d, cleanup_mode="delete")
        yield server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
        server.cleanup()


@pytest.fixture
def db(test_database_url):
    if same_database(test_database_url, get_settings().database_url):
        raise RuntimeError("TEST_DATABASE_URL equals DATABASE_URL, refusing to run")
    engine = create_engine(test_database_url)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    return TestClient(app)
