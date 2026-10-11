import os
from pathlib import Path

import pytest

# Point the app at a throwaway data dir BEFORE app modules are imported,
# so tests never touch the real data/ (which holds real people's voices).
_TMP = Path(os.environ.setdefault("VAANI_TEST_DATA", "/tmp/vaani-test-data"))
os.environ["VAANI_DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
    _TMP.mkdir(parents=True)
    from app.cli import upgrade_to_head

    upgrade_to_head()
    yield
    shutil.rmtree(_TMP, ignore_errors=True)
