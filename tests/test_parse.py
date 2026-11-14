from datetime import UTC, datetime

import pytest

from chessguru.api.contracts import Game
from chessguru.parse.games import (
    ParseError,
    opening_from_url,
    outcome_of,
    parse_game,
    parse_time_control,
)
from tests.factories import make_game

BLACK_SIDE = {"username": "TestPlayer", "rating": 1190, "result": "checkmated"}


def game(**overrides: object) -> Game:
    return Game.model_validate(make_game(1, **overrides))


@pytest.mark.parametrize(
    ("time_control", "expected"),
    [("600", (600, 0)), ("180+2", (180, 2)), ("1/86400", (None, None)), ("", (None, None))],
)
def test_parse_time_control(time_control: str, expected: tuple[int | None, int | None]) -> None:
    assert parse_time_control(time_control) == expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("win", "win"),
        ("agreed", "draw"),
        ("repetition", "draw"),
        ("stalemate", "draw"),
        ("timevsinsufficient", "draw"),
        ("checkmated", "loss"),
        ("resigned", "loss"),
        ("timeout", "loss"),
        ("abandoned", "loss"),
    ],
)
def test_outcome_of(result: str, expected: str) -> None:
    assert outcome_of(result) == expected


@pytest.mark.parametrize(
    ("url", "name", "family"),
    [
        (
            "https://www.chess.com/openings/Sicilian-Defense-Najdorf-Variation-6.Be3",
            "Sicilian Defense Najdorf Variation",
            "Sicilian Defense",
        ),
        (
            "https://www.chess.com/openings/Queens-Pawn-Opening-Accelerated-London-System-2...e6",
            "Queens Pawn Opening Accelerated London System",
            "Queens Pawn Opening",
        ),
        ("https://www.chess.com/openings/Italian-Game", "Italian Game", "Italian Game"),
        ("https://www.chess.com/openings/Englund", "Englund", "Englund"),
        ("https://www.chess.com/openings/1.e4", None, None),
        ("https://example.com/no-openings-here", None, None),
        (None, None, None),
    ],
)
def test_opening_from_url(url: str | None, name: str | None, family: str | None) -> None:
    assert opening_from_url(url) == (name, family)


def test_game_row_from_whites_side() -> None:
    row = parse_game(game(), "testplayer").game

    assert row.player_colour == "white"
    assert row.player_rating == 1200
    assert row.opponent_username == "opponent1"
    assert row.outcome == "win"
    assert row.end_reason == "checkmated"
    assert row.plies == 7
    assert row.base_seconds == 600
    assert row.player_accuracy == 92.1
    assert row.opponent_accuracy == 40.3
    assert row.opening_name == "Bishops Opening"
    assert row.end_time == datetime.fromtimestamp(1793001000, UTC)


def test_game_row_from_blacks_side() -> None:
    row = parse_game(
        game(white={"username": "opp", "rating": 1250, "result": "win"}, black=BLACK_SIDE),
        "testplayer",
    ).game

    assert row.player_colour == "black"
    assert row.outcome == "loss"
    assert row.end_reason == "checkmated"
    assert row.player_accuracy == 40.3


def test_moves() -> None:
    moves = parse_game(game(), "testplayer").moves

    assert [m.san for m in moves] == ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"]
    assert [m.is_player_move for m in moves] == [True, False] * 3 + [True]
    assert [m.move_number for m in moves] == [1, 1, 2, 2, 3, 3, 4]
    last = moves[-1]
    assert (last.piece, last.uci, last.is_capture, last.is_check) == ("Q", "h5f7", True, True)
    assert moves[0].fen_before.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w")


def test_clock_and_time_spent() -> None:
    moves = parse_game(game(), "testplayer").moves

    # Clocks in the PGN: White 598, 595, 590, 585; Black 597, 590, 580 (600s, no increment).
    assert [m.clock_seconds for m in moves] == [598, 597, 595, 590, 590, 580, 585]
    assert [m.time_spent_seconds for m in moves] == [2, 3, 3, 7, 5, 10, 5]


def test_time_spent_includes_increment() -> None:
    moves = parse_game(game(time_control="600+5"), "testplayer").moves

    assert moves[0].time_spent_seconds == 7  # 600 + 5 - 598
    assert moves[2].time_spent_seconds == 8  # 598 + 5 - 595


def test_daily_games_have_no_time_spent() -> None:
    moves = parse_game(game(time_class="daily", time_control="1/86400"), "testplayer").moves

    assert all(m.time_spent_seconds is None for m in moves)


def test_castling_and_promotion_flags() -> None:
    pgn = '[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 *'
    moves = parse_game(game(pgn=pgn), "testplayer").moves

    assert moves[6].san == "O-O"
    assert moves[6].is_castle
    assert moves[6].clock_seconds is None
    assert moves[6].time_spent_seconds is None


@pytest.mark.parametrize(
    ("pgn", "message"),
    [
        ('[Result "*"]\n\n*', "no moves played"),
        ('[Result "*"]\n\n1. e4 e5 2. Ke3 *', "PGN could not be parsed"),
    ],
)
def test_unusable_pgn(pgn: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        parse_game(game(pgn=pgn), "testplayer")


def test_player_must_be_in_game() -> None:
    with pytest.raises(ParseError, match="did not play"):
        parse_game(game(), "someone-else")
