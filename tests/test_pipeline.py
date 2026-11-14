from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from chessguru import pipeline
from chessguru.api.client import BASE_URL, ChessComClient
from chessguru.cli import app
from chessguru.config import Settings
from chessguru.db import connect, logged_run
from tests.factories import archives_json, make_game, month_json

NOW = datetime(2026, 11, 14, tzinfo=UTC)
GAMES = f"{BASE_URL}/player/testplayer/games"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


def mock_api() -> None:
    respx.get(f"{GAMES}/archives").respond(json=archives_json("testplayer", "2026-10"))
    respx.get(f"{GAMES}/2026/10").respond(
        content=month_json(make_game(1), make_game(2), make_game(3, rules="crazyhouse"))
    )


@respx.mock
def test_fetch_then_check_fills_quarantine_and_run_log(settings: Settings) -> None:
    mock_api()
    client = ChessComClient("t", delay=0, sleep=lambda _: None)

    summary = pipeline.fetch(settings, "testplayer", client=client, now=NOW)
    pipeline.check(settings, "testplayer", now=NOW)
    report = pipeline.check(settings, "testplayer", now=NOW)  # re-run is safe

    assert summary.games_found == 3
    assert len(report.valid) == 2
    conn = connect(settings.db_path)
    quarantine = conn.execute("SELECT game_url, reason FROM quarantine").fetchall()
    runs = conn.execute("SELECT step, status FROM pipeline_runs ORDER BY started_at").fetchall()
    assert quarantine == [
        ("https://www.chess.com/game/live/1003", "variant 'crazyhouse' is not supported")
    ]
    assert runs == [("fetch", "succeeded"), ("check", "succeeded"), ("check", "succeeded")]


def test_failed_steps_are_logged(settings: Settings) -> None:
    conn = connect(settings.db_path)

    with pytest.raises(RuntimeError), logged_run(conn, "fetch", "testplayer"):
        raise RuntimeError("network down")

    status, details = conn.execute("SELECT status, details FROM pipeline_runs").fetchone()  # type: ignore[misc]
    assert status == "failed"
    assert "network down" in details


@respx.mock
def test_cli_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(tmp_path))
    mock_api()

    result = CliRunner().invoke(app, ["fetch", "TestPlayer", "--games", "5"])

    assert result.exit_code == 0, result.stdout
    assert "Games ready: 2" in result.stdout
    assert "1 x variant 'crazyhouse' is not supported" in result.stdout


@respx.mock
def test_cli_fetch_unknown_player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(tmp_path))
    respx.get(f"{GAMES}/archives").respond(404)

    result = CliRunner().invoke(app, ["fetch", "testplayer"])

    assert result.exit_code == 1
    assert 'No chess.com player called "testplayer"' in result.stdout


def test_cli_fetch_needs_a_username() -> None:
    result = CliRunner().invoke(app, ["fetch"])

    assert result.exit_code == 2
    assert "Give a username" in result.stdout
