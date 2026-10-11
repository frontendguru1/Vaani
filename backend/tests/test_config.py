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


def test_example_env_file_loads_as_is(tmp_path, monkeypatch):
    """Regression: blank values in a copied .env.example (e.g. VAANI_XTTS_DEVICE=) must
    count as unset, not fail validation."""
    from app.config import REPO_ROOT

    env = tmp_path / ".env"
    env.write_text((REPO_ROOT / ".env.example").read_text())
    monkeypatch.delenv("VAANI_DATA_DIR", raising=False)
    for var in ("DATABASE_URL", "VAANI_TRANSCRIBE_ON_CREATE", "VAANI_DEFAULT_ENGINE"):
        monkeypatch.delenv(var, raising=False)  # set by conftest; env vars outrank .env
    s = Settings(_env_file=env)
    assert s.xtts_device is None and s.f5mlx_quant is None
    assert s.transcribe_on_create is True and s.max_upload_mb == 1024
