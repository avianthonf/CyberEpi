import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add src to path so we can import models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Alembic Config object
config = context.config

# Set sqlalchemy.url from env
db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://cyberepi:devpassword@localhost:5432/cyberepi")
config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging, but don't disable existing loggers
# so startup tracebacks remain visible in container logs
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import models for autogenerate
from src.db.models import Base

target_metadata = Base.metadata

# Use configured version_table (defaults to 'alembic_version' but our ini sets
# 'alembic_version_privacy' so epi-engine and privacy-service don't collide
# in the shared Postgres database).
version_table = config.get_main_option("version_table") or "alembic_version"

# Shared-database guard: every service in this deployment runs against the
# same Postgres database. Without a filter, autogenerate diffs the entire DB
# against this service's metadata and would emit DROP TABLE ops for every
# table owned by other services. Restrict autogen/check to tables this
# service actually owns (i.e., the ones in its own metadata).
_OWN_TABLES = frozenset(t.name for t in target_metadata.tables.values())


def include_name(name: str, type_: str, _reflected: bool) -> bool:
    if type_ == "table":
        return name in _OWN_TABLES
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=version_table,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=version_table,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with asyncpg."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
