"""Run the real dbt project on a small sample database.

This is what CI uses to prove the gold models and their tests work.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from chessguru import pipeline
from chessguru.api.contracts import Game
from chessguru.cli import app
from chessguru.config import Settings
from chessguru.transform.dbt import DEFAULT_PROJECT_DIR, DbtError, run_dbt
from tests.factories import SCHOLARS_MATE, make_game
from tests.fake_engine import FakeEvaluator

NOW = datetime(2026, 11, 14, tzinfo=UTC)
OPP_WIN = {"username": "rival", "rating": 1300, "result": "win"}


def sample_games() -> list[Game]:
    """A mix of colours, results, time classes, openings and rating changes."""
    raw = [
        make_game(1),
        make_game(2, white={"username": "TestPlayer", "rating": 1208, "result": "win"}),
        make_game(
            3,
            white=OPP_WIN,
            black={"username": "TestPlayer", "rating": 1215, "result": "timeout"},
            eco="https://www.chess.com/openings/Sicilian-Defense-Najdorf-Variation-6.Be3",
            # Black is down to 30 seconds of 10 minutes (5%) when playing 3...Nf6??
            pgn=SCHOLARS_MATE.replace("9:40", "0:30"),
        ),
        make_game(
            4,
            time_class="blitz",
            time_control="180+2",
            white={"username": "TestPlayer", "rating": 900, "result": "repetition"},
            black={"username": "rival", "rating": 905, "result": "repetition"},
            accuracies=None,
            eco=None,
        ),
        make_game(5, end_time=1793000000 + 10 * 86400),
    ]
    return [Game.model_validate(g) for g in raw]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    settings = Settings(data_dir=tmp_path_factory.mktemp("data"), hash_key="test-key")
    pipeline.parse(settings, "testplayer", sample_games(), now=NOW)
    # Analyse 4 of the 5 games, so gold has both analysed and unanalysed games.
    pipeline.analyse(settings, "testplayer", max_games=4, make_evaluator=FakeEvaluator)
    result = pipeline.build(settings, "testplayer")
    assert result.failures == []
    assert result.passed > 40
    return settings


def query(settings: Settings, sql: str) -> list[tuple[object, ...]]:
    with duckdb.connect(str(settings.db_path), read_only=True) as conn:
        return conn.execute(sql).fetchall()


def test_fact_game(built: Settings) -> None:
    rows = query(
        built,
        "select game_uuid, outcome, score, player_colour, recency_rank "
        "from gold.fact_game order by game_uuid",
    )

    assert rows == [
        ("uuid-1", "win", 1.0, "white", 5),
        ("uuid-2", "win", 1.0, "white", 4),
        ("uuid-3", "loss", 0.0, "black", 3),
        ("uuid-4", "draw", 0.5, "white", 2),
        ("uuid-5", "win", 1.0, "white", 1),
    ]


def test_fact_move_grain(built: Settings) -> None:
    assert query(built, "select count(*), count(distinct game_key) from gold.fact_move") == [
        (35, 5)
    ]


def test_dim_player_keeps_rating_history(built: Settings) -> None:
    rows = query(
        built,
        "select time_class, rating, is_current from gold.dim_player "
        "order by time_class, valid_from",
    )

    assert rows == [
        ("blitz", 900, True),
        ("rapid", 1200, False),
        ("rapid", 1208, False),
        ("rapid", 1215, False),
        ("rapid", 1200, True),
    ]


def test_fact_game_uses_the_rating_row_valid_at_the_time(built: Settings) -> None:
    rows = query(
        built,
        "select f.game_uuid, p.rating from gold.fact_game f "
        "join gold.dim_player p using (player_key) order by f.game_uuid",
    )

    assert rows == [
        ("uuid-1", 1200),
        ("uuid-2", 1208),
        ("uuid-3", 1215),
        ("uuid-4", 900),
        ("uuid-5", 1200),
    ]


def test_opponents_are_hashed(built: Settings) -> None:
    keys = [r[0] for r in query(built, "select opponent_key from gold.dim_opponent")]

    assert len(keys) == 4  # opponent1, opponent2, rival (twice), opponent5
    assert not any("rival" in str(k) or "opponent" in str(k) for k in keys)


def test_time_control_labels(built: Settings) -> None:
    rows = query(built, "select time_control, label from gold.dim_time_control order by 1")

    assert rows == [("180+2", "3 min + 2s"), ("600", "10 min")]


def test_opening_mart(built: Settings) -> None:
    rows = query(
        built,
        "select opening_family, player_colour, games, points, score_pct "
        "from gold.mart_opening_performance order by opening_family, player_colour",
    )

    assert rows == [
        ("Bishops Opening", "white", 3, 3.0, 1.0),
        ("Sicilian Defense", "black", 1, 0.0, 0.0),
        ("Unknown", "white", 1, 0.5, 0.5),
    ]


def test_build_is_safe_to_rerun(built: Settings) -> None:
    result = pipeline.build(built, "testplayer")

    assert result.failures == []
    assert query(built, "select count(*) from gold.fact_game") == [(5,)]
    assert query(
        built, "select status from pipeline_runs where step = 'build' order by started_at"
    ) == [("succeeded",), ("succeeded",)]


def test_failing_dbt_test_is_reported(built: Settings, tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(DEFAULT_PROJECT_DIR, project, ignore=shutil.ignore_patterns("target", "logs"))
    (project / "tests" / "assert_always_fails.sql").write_text("select 1 as bad_row")

    result = run_dbt(built, "build", project_dir=project)

    assert result.failures == ["assert_always_fails: Got 1 result, configured to fail if != 0"]


def test_broken_project_raises(built: Settings, tmp_path: Path) -> None:
    (tmp_path / "dbt_project.yml").write_text("not: [valid")

    with pytest.raises(DbtError, match="could not run"):
        run_dbt(built, "build", project_dir=tmp_path)


def test_missing_project(built: Settings, tmp_path: Path) -> None:
    with pytest.raises(DbtError, match="No dbt project"):
        run_dbt(built, "build", project_dir=tmp_path)


def test_cli_build_and_docs(built: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(built.data_dir))
    runner = CliRunner()

    build = runner.invoke(app, ["build"])
    docs = runner.invoke(app, ["docs"])

    assert build.exit_code == 0, build.stdout
    assert "models and tests passed" in build.stdout
    assert docs.exit_code == 0, docs.stdout
    assert (built.dbt_target_dir / "index.html").exists()
    assert (built.dbt_target_dir / "catalog.json").exists()


def test_analysis_reaches_gold(built: Settings) -> None:
    rows = query(
        built,
        "select game_uuid, is_analysed, blunders, failed_to_convert "
        "from gold.fact_game order by game_uuid",
    )

    # uuid-1 is the oldest game, so it is the one left unanalysed.
    assert [r[:2] for r in rows] == [
        ("uuid-1", False),
        ("uuid-2", True),
        ("uuid-3", True),
        ("uuid-4", True),
        ("uuid-5", True),
    ]
    assert rows[0][2] is None
    # In uuid-3 the player is Black and walks into Scholar's mate.
    assert isinstance(rows[2][2], int) and rows[2][2] >= 1


def test_mistake_patterns(built: Settings) -> None:
    rows = query(
        built,
        "select tag, phase, moves from gold.mart_mistake_patterns where tag = 'allowed_mate'",
    )

    assert rows == [("allowed_mate", "opening", 1)]
    low_clock = query(built, "select moves from gold.mart_mistake_patterns where tag = 'low_clock'")
    assert low_clock == [(1,)]


def test_phase_accuracy(built: Settings) -> None:
    rows = query(
        built,
        "select phase, sum(games), sum(moves), sum(blunders) "
        "from gold.mart_phase_accuracy group by 1",
    )

    # 4 analysed games, all short enough to stay in the opening; 15 of the moves are ours.
    assert rows == [("opening", 4, 15, 1)]
