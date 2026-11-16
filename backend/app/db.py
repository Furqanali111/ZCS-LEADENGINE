from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# Importing this module needs DATABASE_URL set; the engine only connects on first use.
# Small pool: every teammate's copy shares the free Supabase pooler (15 real connections).
# prepare_threshold=None: the pooler's transaction mode (port 6543) cannot keep prepared statements.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
    pool_recycle=300,
    connect_args={"prepare_threshold": None},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
