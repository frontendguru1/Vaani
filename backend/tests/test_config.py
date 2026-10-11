from pathlib import Path

from app.config import REPO_ROOT, Settings


def test_relative_data_dir_resolves_from_repo_root():
    s = Settings(data_dir=Path("somewhere"), DATABASE_URL="")
    assert s.data_dir == (REPO_ROOT / "somewhere").resolve()
    assert s.db_url == f"sqlite:///{s.data_dir / 'vaani.db'}"


def test_database_url_overrides_sqlite_default():
    s = Settings(DATABASE_URL="postgresql+psycopg://u:p@localhost/vaani")
    assert s.db_url.startswith("postgresql")


def test_feature_flags_parse_from_comma_string():
    s = Settings(features="dialogue, srt,,")
    assert s.features == {"dialogue", "srt"}
    assert s.feature_enabled("srt") and not s.feature_enabled("batch")
