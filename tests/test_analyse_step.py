"""The analyse step: picking games, running engines in parallel, saving results."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chessguru import pipeline
from chessguru.analysis.engine import EngineError
from chessguru.api.contracts import Game
from chessguru.cli import app
from chessguru.config import Settings
from chessguru.db import connect
from tests.factories import make_game
from tests.fake_engine import FakeEvaluator

NOW = datetime(2026, 11, 14, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path / "data")
    games = [Game.model_validate(make_game(n)) for n in range(1, 6)]
    pipeline.parse(settings, "testplayer", games, now=NOW)
    return settings


def test_analyses_only_the_newest_games(settings: Settings) -> None:
    engines: list[FakeEvaluator] = []

    def make() -> FakeEvaluator:
        engines.append(FakeEvaluator())
        return engines[-1]

    summary = pipeline.analyse(settings, "testplayer", max_games=2, make_evaluator=make, workers=2)

    assert (summary.selected, summary.analysed, summary.already_done) == (2, 2, 0)
    conn = connect(settings.db_path)
    done = conn.execute("select game_uuid from silver_game_analysis order by 1").fetchall()
    assert done == [("uuid-4",), ("uuid-5",)]  # factory games get newer as n grows
    assert conn.execute("select count(*) from silver_move_evals").fetchone() == (14,)
    assert all(engine.closed for engine in engines)


def test_more_games_only_analyses_the_extra_ones(settings: Settings) -> None:
    pipeline.analyse(settings, "testplayer", max_games=2, make_evaluator=FakeEvaluator)
    progress: list[tuple[int, int]] = []

    summary = pipeline.analyse(
        settings,
        "testplayer",
        max_games=4,
        make_evaluator=FakeEvaluator,
        workers=1,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert (summary.selected, summary.analysed, summary.already_done) == (4, 2, 2)
    assert progress == [(1, 2), (2, 2)]


def test_deeper_analysis_redoes_games(settings: Settings) -> None:
    pipeline.analyse(settings, "testplayer", max_games=2, make_evaluator=FakeEvaluator)
    deeper = settings.model_copy(update={"engine_depth": settings.engine_depth + 4})

    summary = pipeline.analyse(deeper, "testplayer", max_games=2, make_evaluator=FakeEvaluator)

    assert summary.analysed == 2
    conn = connect(settings.db_path)
    assert conn.execute("select count(*) from silver_move_evals").fetchone() == (14,)
    assert conn.execute("select distinct engine_depth from silver_game_analysis").fetchone() == (
        settings.engine_depth + 4,
    )


def test_nothing_to_do(settings: Settings) -> None:
    pipeline.analyse(settings, "testplayer", max_games=5, make_evaluator=FakeEvaluator)

    summary = pipeline.analyse(settings, "testplayer", max_games=5, make_evaluator=FakeEvaluator)

    assert (summary.analysed, summary.already_done) == (0, 5)


def test_missing_stockfish(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("chessguru.config.STOCKFISH_LOCATIONS", ())

    with pytest.raises(EngineError, match="Stockfish was not found"):
        pipeline.analyse(settings, "testplayer")


def test_cli_analyse_without_stockfish(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(settings.data_dir))
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("chessguru.config.STOCKFISH_LOCATIONS", ())

    result = CliRunner().invoke(app, ["analyse", "testplayer", "--games", "3"])

    assert result.exit_code == 1
    assert "Stockfish was not found" in result.stdout


def test_cli_analyse_with_fake_engine(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(settings.data_dir))
    monkeypatch.setattr(
        "chessguru.pipeline.StockfishEvaluator", lambda path, depth: FakeEvaluator()
    )
    monkeypatch.setenv("CHESSGURU_STOCKFISH_PATH", str(settings.db_path))  # any existing file

    result = CliRunner().invoke(app, ["analyse", "testplayer", "--games", "3", "--depth", "6"])

    assert result.exit_code == 0, result.stdout
    assert "newest 3 games at depth 6" in result.stdout
    assert "Analysed 3 games (0 were already done)" in result.stdout


def test_only_analyses_the_chosen_games(settings: Settings) -> None:
    summary = pipeline.analyse(
        settings,
        "testplayer",
        max_games=10,
        make_evaluator=FakeEvaluator,
        only=["uuid-1", "uuid-3"],
    )

    assert (summary.selected, summary.analysed) == (2, 2)
    conn = connect(settings.db_path)
    done = conn.execute("select game_uuid from silver_game_analysis order by 1").fetchall()
    assert done == [("uuid-1",), ("uuid-3",)]


class BrokenEvaluator(FakeEvaluator):
    """Fails on its first position, like a crashed engine."""

    def evaluate(self, board):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise EngineError("Stockfish failed")


def test_a_failing_game_stops_the_rest(settings: Settings) -> None:
    engine = BrokenEvaluator()

    with pytest.raises(EngineError):
        pipeline.analyse(
            settings, "testplayer", max_games=5, make_evaluator=lambda: engine, workers=1
        )

    assert engine.calls <= 2  # the queued games were cancelled, not run
    assert engine.closed
