from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  registers tables on Base.metadata
from app.config import get_settings
from app.db import Base

target_metadata = Base.metadata


def get_url() -> str:
    # `-x db_url=...` lets tests and dry runs target another database; never printed.
    return context.get_x_argument(as_dictionary=True).get("db_url") or get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
