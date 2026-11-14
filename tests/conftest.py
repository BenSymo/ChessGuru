import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Keep tests independent of the developer's own .env and environment."""
    import os

    for key in list(os.environ):
        if key.startswith("CHESSGURU_"):
            monkeypatch.delenv(key)
    # Run from an empty folder so no .env file is picked up.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
