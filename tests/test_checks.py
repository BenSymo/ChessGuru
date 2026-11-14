"""Data quality checks: contract, duplicates, variants, freshness and the stop rule."""

import json
from datetime import UTC, datetime

import pytest

from chessguru.quality.checks import DataContractError, check_games
from tests.factories import make_game, month_json

NOW = datetime(2026, 11, 14, tzinfo=UTC)  # factory games end around late Oct 2026


def run(*games: dict[str, object], raw: bytes | None = None):  # type: ignore[no-untyped-def]
    return check_games("testplayer", [("2026-10.json", raw or month_json(*games))], NOW)


def test_good_games_pass() -> None:
    black_game = make_game(
        2,
        white={"username": "someone", "rating": 1250, "result": "win"},
        black={"username": "TESTPLAYER", "rating": 1200, "result": "timeout"},
    )

    report = run(make_game(1), black_game)

    assert [g.uuid for g in report.valid] == ["uuid-1", "uuid-2"]
    assert report.rejected == []
    assert report.warnings == []
    assert report.valid[1].colour_of("testplayer") == "black"


@pytest.mark.parametrize(
    ("bad_game", "reason"),
    [
        (make_game(9, rules="chess960"), "variant 'chess960' is not supported"),
        (make_game(9, initial_setup="8/8/8/8/8/8/8/K6k w - - 0 1"), "custom start position"),
        (
            make_game(9, white={"username": "a", "rating": 1, "result": "win"}),
            "testplayer did not play in this game",
        ),
        (make_game(9, pgn=""), "breaks data contract: pgn"),
        (make_game(9, time_class="hyperbullet"), "breaks data contract: time_class"),
        (make_game(9, url="https://evil.example/game/1"), "breaks data contract: url"),
    ],
)
def test_bad_games_are_quarantined(bad_game: dict[str, object], reason: str) -> None:
    report = run(make_game(1), make_game(2), bad_game)

    assert len(report.valid) == 2
    assert len(report.rejected) == 1
    assert report.rejected[0].reason.startswith(reason)
    assert report.rejected[0].source == "2026-10.json"


def test_missing_field_is_a_contract_break() -> None:
    game = make_game(9)
    del game["white"]

    report = run(make_game(1), make_game(2), game)

    assert report.rejected[0].reason.startswith("breaks data contract: white")
    assert report.rejected[0].game_url == game["url"]


def test_duplicates_are_quarantined_across_months() -> None:
    months = [
        ("2026-09.json", month_json(make_game(1))),
        ("2026-10.json", month_json(make_game(1))),
    ]

    report = check_games("testplayer", months, NOW)

    assert len(report.valid) == 1
    assert report.rejected[0].reason == "duplicate game"


def test_unreadable_month_file() -> None:
    report = run(raw=b"<html>oops</html>")

    assert report.rejected[0].reason == "month file is not readable JSON"
    assert "No games passed the checks." in report.warnings


def test_extra_fields_are_allowed() -> None:
    report = run(make_game(1, brand_new_field={"x": 1}))

    assert len(report.valid) == 1


def test_stops_when_most_games_break_the_contract() -> None:
    broken = [make_game(n, time_class="?") for n in range(3)]

    with pytest.raises(DataContractError, match="3 of 4"):
        run(make_game(10), *broken)


def test_warns_when_games_are_old() -> None:
    report = check_games(
        "testplayer",
        [("x.json", month_json(make_game(1)))],
        datetime(2027, 6, 1, tzinfo=UTC),
    )

    assert len(report.valid) == 1
    assert report.warnings[0].startswith("Newest game is from")


def test_end_time_is_parsed_as_utc_datetime() -> None:
    report = run(make_game(1))

    assert report.valid[0].end_time == datetime.fromtimestamp(1793001000, UTC)
    assert json.loads(month_json(make_game(1)))["games"][0]["end_time"] == 1793001000
