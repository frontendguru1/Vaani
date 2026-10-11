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


def test_table_rebuild_migrations_keep_child_rows(tmp_path):
    """Regression: SQLite batch mode rebuilds a table by DROPping it; with foreign keys ON
    that cascaded and deleted every child row (all generation_chunks when the batches
    migration rebuilt `generations`). env.py turns foreign keys off while migrating."""
    from sqlalchemy import text

    url = _url(tmp_path)
    cfg = alembic_config(url)
    command.upgrade(cfg, "06f5dbbf761c")  # the revision before `batches`
    engine = make_engine(url)
    now = "2026-10-11 00:00:00"
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO voices (id,name,language,description,consent_note,status,"
                "speech_seconds,sort_order,source,created_at,updated_at) VALUES "
                "('v1','V','en','','ok consent note','ready',0,0,'user',:t,:t)"
            ),
            {"t": now},
        )
        c.execute(
            text(
                "INSERT INTO generations (id,voice_id,engine,language,script,settings,"
                "status,chunk_count,created_at,updated_at) VALUES "
                "('g1','v1','xtts','en','Hi.','{}','done',1,:t,:t)"
            ),
            {"t": now},
        )
        c.execute(
            text(
                "INSERT INTO generation_chunks (id,generation_id,idx,text,char_start,"
                "char_end,pause_after_ms,status,created_at,updated_at) VALUES "
                "('c1','g1',0,'Hi.',0,3,0,'done',:t,:t)"
            ),
            {"t": now},
        )
    engine.dispose()
    command.upgrade(cfg, "head")  # rebuilds `generations` to add its batch foreign key
    engine = make_engine(url)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM generation_chunks")).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM generations")).scalar() == 1
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1  # back on for the app
    engine.dispose()
