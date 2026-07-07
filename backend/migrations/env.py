"""Alembic env — schema-first, чистый SQL.

Никакого ``target_metadata``/autogenerate: схемой владеют SQL-файлы в
``migrations/sql/``, а не ORM-модели. URL берём из ``DATABASE_URL_SYNC``
(sync-драйвер psycopg — Alembic работает синхронно).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Единственная строка подключения — DATABASE_URL (async); Settings читает
# backend/.env, а для Alembic берём производный sync-URL (psycopg). База одна.
config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)

target_metadata = None  # schema-first: autogenerate отключён намеренно


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
