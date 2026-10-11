"""Maintenance commands:  uv run vaani <command>

init-db          create data dirs and bring the schema to head
migrate          apply pending migrations (alias of init-db for an existing DB)
make-migration   autogenerate a new migration:  vaani make-migration "add voices"
reset-dev-data   DELETE all voices, generations and the DB (keeps downloaded models)
check            consistency check (schema at head; orphaned files/rows from Phase 2)
"""

import argparse
import shutil
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade_to_head(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")


def schema_is_current(url: str | None = None) -> tuple[bool, str | None, str | None]:
    from app.db import make_engine

    cfg = alembic_config(url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = make_engine(url or get_settings().db_url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    return current == head, current, head


def cmd_init_db(_args: argparse.Namespace) -> int:
    get_settings().ensure_dirs()
    upgrade_to_head()
    print(f"Database ready: {get_settings().db_url}")
    return 0


def cmd_make_migration(args: argparse.Namespace) -> int:
    command.revision(alembic_config(), message=args.message, autogenerate=True)
    return 0


def cmd_reset_dev_data(args: argparse.Namespace) -> int:
    settings = get_settings()
    targets = [settings.data_dir / d for d in ("voices", "generations", "benchmarks")]
    db_files = list(settings.data_dir.glob("vaani.db*"))
    print("This permanently deletes:")
    for t in [*targets, *db_files]:
        print(f"  {t}")
    if not args.yes and input("Type 'delete' to continue: ").strip() != "delete":
        print("Aborted.")
        return 1
    for t in targets:
        shutil.rmtree(t, ignore_errors=True)
    for f in db_files:
        f.unlink(missing_ok=True)
    settings.ensure_dirs()
    upgrade_to_head()
    print("Dev data reset. Models in data/models were kept.")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    ok, current, head = schema_is_current()
    print(f"schema: {'OK' if ok else 'BEHIND'} (db={current}, head={head})")
    # Orphaned file/row detection is added with the voices tables in Phase 2.
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vaani", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("migrate").set_defaults(func=cmd_init_db)
    mk = sub.add_parser("make-migration")
    mk.add_argument("message")
    mk.set_defaults(func=cmd_make_migration)
    reset = sub.add_parser("reset-dev-data")
    reset.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    reset.set_defaults(func=cmd_reset_dev_data)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
