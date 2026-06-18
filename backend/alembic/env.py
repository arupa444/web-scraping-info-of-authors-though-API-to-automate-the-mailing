"""Alembic environment — uses iceReach's metadata and configured database URL."""

import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the icereach package importable (backend/ on path).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from icereach.config import settings  # noqa: E402
from icereach.db import Base  # noqa: E402
import icereach.models  # noqa: E402,F401  (populate metadata)

config = context.config
# Prefer an explicit DATABASE_URL at migration time (CI, tests, ops); fall back to settings.
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL") or settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url, target_metadata=target_metadata,
        literal_binds=True, render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
