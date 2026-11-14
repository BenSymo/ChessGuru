from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chessguru.config import Settings

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


@pytest.fixture(scope="session")
def gold_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """A small gold database built from the sample games, shared by the dashboard tests."""
    from datetime import UTC, datetime

    from chessguru import pipeline
    from chessguru.config import Settings
    from tests.factories import sample_games
    from tests.fake_engine import FakeEvaluator

    settings = Settings(
        data_dir=tmp_path_factory.mktemp("gold"), hash_key="test-key", username="testplayer"
    )
    now = datetime(2026, 11, 14, tzinfo=UTC)
    pipeline.parse(settings, "testplayer", sample_games(), now=now)
    pipeline.analyse(settings, "testplayer", max_games=4, make_evaluator=FakeEvaluator)
    result = pipeline.build(settings, "testplayer")
    assert result.failures == []
    return settings
