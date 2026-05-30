import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point elenchos at a temp data directory for every test."""
    monkeypatch.setattr("elenchos.config._cli_data_dir", tmp_path)
