from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import get_settings
from app.db import make_engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # Tests (and tools) may override the URL via `config.set_main_option`.
    return config.get_main_option("sqlalchemy.url") or get_settings().db_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    connectable = make_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        sqlite = url.startswith("sqlite")
        if sqlite:
            # Batch mode rebuilds a table by copying it and DROPping the original. With
            # foreign keys ON, that DROP fires ON DELETE CASCADE and silently deletes every
            # child row (e.g. all generation_chunks when `generations` is rebuilt). Must be
            # set outside a transaction.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            # exec_driver_sql autobegins a transaction; end it, or Alembic's transaction
            # becomes nested inside it and never commits (the downgrade test caught this).
            connection.commit()
        # render_as_batch: SQLite can't ALTER most things; batch mode copies the table.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            problems = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if problems:
                raise RuntimeError(f"Migration left broken foreign keys: {problems[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
