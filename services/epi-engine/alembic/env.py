import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from src.config import settings

# Import models to populate metadata
from src.db.models import Base

# this is the Alembic Config object, which provides
config = context.config
# Override the hardcoded URL from alembic.ini with the runtime setting.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata
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


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=version_table,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncpg."""
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
