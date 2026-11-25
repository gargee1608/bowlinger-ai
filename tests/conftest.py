import pytest

from bowlinger.config import Settings


@pytest.fixture
def settings(tmp_path):
    data = tmp_path / "data"
    return Settings(db_path=data / "bowlinger.db", data_dir=data, sync_jobs=True)
