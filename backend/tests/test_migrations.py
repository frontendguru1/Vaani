from alembic import command
from sqlalchemy import inspect

from app.cli import alembic_config, schema_is_current, upgrade_to_head
from app.db import make_engine
from app.models import Base


def _url(tmp_path):
    return f"sqlite:///{tmp_path / 'm.db'}"


def test_upgrade_creates_all_model_tables(tmp_path):
    url = _url(tmp_path)
    upgrade_to_head(url)
    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert set(Base.metadata.tables) <= tables


def test_downgrade_to_base_and_back(tmp_path):
    url = _url(tmp_path)
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = make_engine(url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
    command.upgrade(cfg, "head")
    assert schema_is_current(url)[0]


def test_models_match_migrations(tmp_path):
    """Fails if someone changed a model without writing a migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    url = _url(tmp_path)
    upgrade_to_head(url)
    engine = make_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_sqlite_runs_in_wal_mode(tmp_path):
    engine = make_engine(_url(tmp_path))
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    engine.dispose()
    assert mode == "wal"
