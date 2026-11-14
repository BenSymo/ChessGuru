"""Dashboard tests: the summaries on known data, and every page renders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from chessguru.app import aggregates, data
from chessguru.config import Settings

MAIN = Path(__file__).parents[1] / "src" / "chessguru" / "app" / "main.py"
PAGES = [
    "overview",
    "tips",
    "openings",
    "mistakes",
    "time_management",
    "endgames",
    "game_viewer",
    "health",
]


@pytest.fixture
def games(gold_settings: Settings) -> pd.DataFrame:
    return data.load_games(gold_settings.db_path, data.Filters("testplayer"))


@pytest.fixture
def moves(gold_settings: Settings, games: pd.DataFrame) -> pd.DataFrame:
    keys = list(games.loc[games["is_analysed"], "game_key"])
    return data.load_moves(gold_settings.db_path, "testplayer", keys)


# --- data --------------------------------------------------------------------


def test_usernames(gold_settings: Settings, tmp_path: Path) -> None:
    assert data.usernames(gold_settings.db_path) == ["testplayer"]
    assert data.usernames(tmp_path / "missing.duckdb") == []


def test_games_newest_first(games: pd.DataFrame) -> None:
    assert list(games["game_uuid"]) == ["uuid-5", "uuid-4", "uuid-3", "uuid-2", "uuid-1"]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (data.Filters("testplayer", colour="black"), ["uuid-3"]),
        (data.Filters("testplayer", time_classes=("blitz",)), ["uuid-4"]),
        (data.Filters("testplayer", last_n=2), ["uuid-5", "uuid-4"]),
        (data.Filters("testplayer", time_classes=("rapid",), last_n=2), ["uuid-5", "uuid-3"]),
        (data.Filters("nobody"), []),
    ],
)
def test_filters(gold_settings: Settings, filters: data.Filters, expected: list[str]) -> None:
    assert list(data.load_games(gold_settings.db_path, filters)["game_uuid"]) == expected


def test_moves_are_the_players_analysed_moves(moves: pd.DataFrame) -> None:
    assert len(moves) == 15  # 4 analysed games; see test_dbt
    assert moves["game_key"].nunique() == 4


def test_no_moves_for_no_games(gold_settings: Settings) -> None:
    assert data.load_moves(gold_settings.db_path, "testplayer", []).empty


def test_missing_database(tmp_path: Path) -> None:
    with pytest.raises(data.DataUnavailable, match="No database"):
        data.load_games(tmp_path / "nope.duckdb", data.Filters("x"))


def test_database_without_gold(tmp_path: Path) -> None:
    from chessguru.db import connect

    connect(tmp_path / "db.duckdb").close()

    with pytest.raises(data.DataUnavailable, match="aren't built"):
        data.load_games(tmp_path / "db.duckdb", data.Filters("x"))


def test_health(gold_settings: Settings) -> None:
    info = data.health(gold_settings.db_path)

    counts = dict(zip(info["counts"]["layer"], info["counts"]["rows"], strict=True))
    assert counts["Silver games"] == 5
    assert counts["Analysed games"] == 4
    assert set(info["runs"]["step"]) >= {"parse", "analyse", "build"}


# --- aggregates --------------------------------------------------------------


def test_summary(games: pd.DataFrame) -> None:
    s = aggregates.summary(games)

    assert (s.games, s.wins, s.draws, s.losses, s.analysed) == (5, 3, 1, 1, 4)
    assert s.score_pct == pytest.approx(3.5 / 5)
    assert s.blunders_per_game is not None and s.blunders_per_game > 0


def test_summary_of_nothing(games: pd.DataFrame) -> None:
    s = aggregates.summary(games.head(0))

    assert (s.games, s.score_pct, s.accuracy) == (0, None, None)


def test_rating_trend(games: pd.DataFrame) -> None:
    trend = aggregates.rating_trend(games)

    rapid = trend[trend["time_class"] == "rapid"]
    assert list(rapid["rating"]) == [1200, 1208, 1215, 1200]
    assert aggregates.rating_trend(games.head(0)).empty


def test_phase_stats(moves: pd.DataFrame) -> None:
    stats = aggregates.phase_stats(moves).set_index("phase")

    assert stats.loc["opening", "moves"] == 15
    assert stats.loc["endgame", "games"] == 0
    assert pd.isna(stats.loc["endgame", "blunders_per_game"])


def test_mistake_types(moves: pd.DataFrame) -> None:
    types = aggregates.mistake_types(moves).set_index("tag")

    assert types.loc["allowed_mate", "moves"] == 1
    assert types.loc["low_clock", "name"] == "Short of time"
    assert aggregates.mistake_types(moves.head(0)).empty


def test_worst_moves(moves: pd.DataFrame, games: pd.DataFrame) -> None:
    worst = aggregates.worst_moves(moves, games, limit=1)

    assert worst.iloc[0]["san"] == "Nf6"
    assert worst.iloc[0]["url"].startswith("https://www.chess.com/game/")


def test_opening_table(games: pd.DataFrame) -> None:
    table = aggregates.opening_table(games, min_games=2)

    assert list(table["opening_family"]) == ["Bishops Opening"]
    assert table.iloc[0]["games"] == 3


def test_time_by_move_and_clock(moves: pd.DataFrame, games: pd.DataFrame) -> None:
    profile = aggregates.time_by_move(moves, games)
    by_clock = aggregates.bad_moves_by_clock(moves).set_index("clock_left")

    assert profile.empty  # fewer than 5 samples per move number in the sample data
    assert by_clock.loc["Under 10%", "moves"] == 1
    assert by_clock.loc["Under 10%", "bad_rate"] == 1.0


def test_time_losses_and_endings(games: pd.DataFrame) -> None:
    assert aggregates.time_losses(games) == {
        "losses": 1,
        "lost_on_time": 1,
        "lost_on_time_while_winning": 0,
    }
    endings = aggregates.endings(games)
    assert set(endings["name"]) >= {"Ran out of time", "Checkmated", "Repetition"}


def test_conversion(games: pd.DataFrame) -> None:
    conv = aggregates.conversion(games)

    assert conv.winning_games == conv.won + conv.drawn + conv.lost
    assert conv.rate is None or 0 <= conv.rate <= 1


# --- pages render --------------------------------------------------------------


def _render_page(name: str) -> None:
    import importlib

    from chessguru.app import data
    from chessguru.app.charts import LIGHT
    from chessguru.app.context import Context, set_context
    from chessguru.config import Settings

    settings = Settings()
    filters = data.Filters(settings.username or "")
    games = data.load_games(settings.db_path, filters)
    keys = list(games.loc[games["is_analysed"], "game_key"])
    moves = data.load_moves(settings.db_path, filters.username, keys)
    set_context(Context(settings, filters, games, moves, LIGHT))
    importlib.import_module(f"chessguru.app.views.{name}").render()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page: str, gold_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(gold_settings.data_dir))
    monkeypatch.setenv("CHESSGURU_USERNAME", "testplayer")

    app = AppTest.from_function(_render_page, args=(page,), default_timeout=30).run()

    assert not app.exception, app.exception
    assert app.title[0].value


def test_main_app_renders_overview(
    gold_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(gold_settings.data_dir))

    app = AppTest.from_file(str(MAIN), default_timeout=30).run()

    assert not app.exception, app.exception
    assert app.title[0].value == "Overview"
    assert app.sidebar.number_input[0].value == 5  # all 5 sample games (default 30, capped)
    assert any("4 of 5 games shown are analysed" in c.value for c in app.sidebar.caption)


def test_main_app_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(tmp_path))

    app = AppTest.from_file(str(MAIN), default_timeout=30).run()

    assert not app.exception, app.exception
    assert app.title[0].value == "ChessGuru"
    assert app.text_input[0].label == "Your chess.com username"
