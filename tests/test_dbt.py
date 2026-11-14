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
from chessguru.cli import app
from chessguru.config import Settings
from chessguru.transform.dbt import DEFAULT_PROJECT_DIR, DbtError, run_dbt
from tests.factories import sample_games
from tests.fake_engine import FakeEvaluator

NOW = datetime(2026, 11, 14, tzinfo=UTC)


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


def query(
    settings: Settings, sql: str, params: list[object] | None = None
) -> list[tuple[object, ...]]:
    with duckdb.connect(str(settings.db_path), read_only=True) as conn:
        return conn.execute(sql, params or []).fetchall()


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


def test_results_by_opening(built: Settings) -> None:
    rows = query(
        built,
        "select o.opening_family, f.player_colour, count(*), sum(f.score), avg(f.score) "
        "from gold.fact_game f join gold.dim_opening o using (opening_key) "
        "group by all order by 1, 2",
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


BAD_MOVE_TAGS = (
    "select tag, phase, count(*) from ("
    "  select unnest(tags) as tag, phase from gold.fact_move"
    "  where is_player_move and is_bad_move"
    ") where tag = ? group by all"
)


def test_bad_move_reasons(built: Settings) -> None:
    assert query(built, BAD_MOVE_TAGS, ["allowed_mate"]) == [("allowed_mate", "opening", 1)]
    # low_clock is added by dbt, not by the analysis step.
    assert query(built, BAD_MOVE_TAGS, ["low_clock"]) == [("low_clock", "opening", 1)]


def test_phase_accuracy(built: Settings) -> None:
    rows = query(
        built,
        "select phase, count(distinct game_key), count(*), count(*) filter (label = 'blunder') "
        "from gold.fact_move where is_player_move and is_analysed group by 1",
    )

    # 4 analysed games, all short enough to stay in the opening; 15 of the moves are ours.
    assert rows == [("opening", 4, 15, 1)]


def test_build_time_includes_dbt(built: Settings) -> None:
    rows = query(
        built, "select epoch(finished_at - started_at) from pipeline_runs where step = 'build'"
    )

    assert all(isinstance(r[0], float) and r[0] > 1 for r in rows)  # dbt takes a few seconds
