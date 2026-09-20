import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep app state out of the developer's personal library by default."""
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(tmp_path / "tiklocal-data"))
