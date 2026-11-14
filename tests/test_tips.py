"""Tip rules on small, hand-built tables, so each rule's behaviour is clear."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from chessguru.cli import app
from chessguru.config import Settings
from chessguru.insights import tips

START = datetime(2026, 11, 1, 12, tzinfo=UTC)
FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def make_games(n: int, **columns: Any) -> pd.DataFrame:
    """n games, one every 3 hours (so no tilt by default). Columns may be lists or values."""
    frame = pd.DataFrame(
        {
            "game_key": [f"g{i}" for i in range(n)],
            "url": [f"https://www.chess.com/game/live/{i}" for i in range(n)],
            "end_time": [START + timedelta(hours=3 * i) for i in range(n)],
            "date_day": [date(2026, 11, 1)] * n,
            "time_class": "blitz",
            "player_colour": ["white" if i % 2 == 0 else "black" for i in range(n)],
            "opening_family": "Italian Game",
            "outcome": "win",
            "score": 1.0,
            "end_reason": "resigned",
            "is_analysed": True,
            "peak_win_chance": 60.0,
        }
    )
    for name, value in columns.items():
        frame[name] = value
    return frame


def make_moves(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Player moves. Defaults: a harmless middlegame move."""
    defaults: dict[str, Any] = {
        "ply": 21,
        "san": "e5",
        "best_move_san": "d5",
        "fen_before": FEN,
        "phase": "middlegame",
        "label": "good",
        "is_bad_move": False,
        "win_before": 50.0,
        "win_after": 50.0,
        "win_drop": 0.0,
        "move_accuracy": 95.0,
        "tags": [],
    }
    columns = ["game_key", *defaults]
    return pd.DataFrame([{**defaults, **row} for row in rows], columns=columns)


def blunder(game: str, drop: float, tags: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "game_key": game,
        "label": "blunder",
        "is_bad_move": True,
        "win_drop": drop,
        "win_after": 50 - drop,
        "move_accuracy": 20.0,
        "tags": tags,
        **extra,
    }


def ids(found: list[tips.Tip]) -> list[str]:
    return [t.id for t in found]


# --- tag rules ---------------------------------------------------------------


def test_tag_rule_needs_two_games() -> None:
    games = make_games(10)
    one_game = make_moves(
        [blunder("g1", 40, ["hanging_piece"]), blunder("g1", 30, ["hanging_piece"], ply=31)]
    )
    two_games = make_moves(
        [blunder("g1", 40, ["hanging_piece"]), blunder("g2", 30, ["hanging_piece"])]
    )

    assert "hanging_pieces" not in ids(tips.tag_tips(games, one_game))
    [tip] = [t for t in tips.tag_tips(games, two_games) if t.id == "hanging_pieces"]
    assert tip.cost == pytest.approx(0.7)
    assert (tip.games_affected, tip.based_on) == (2, 10)
    assert tip.examples[0].played == "e5" and tip.examples[0].win_drop == 40


def test_cost_is_capped_at_one_game_per_game() -> None:
    moves = make_moves(
        [
            blunder("g1", 80, ["hanging_piece"]),
            blunder("g1", 70, ["hanging_piece"], ply=40),
            blunder("g2", 20, ["hanging_piece"]),
        ]
    )

    [tip] = [t for t in tips.tag_tips(make_games(10), moves) if t.id == "hanging_pieces"]
    assert tip.cost == pytest.approx(1.0 + 0.2)


def test_missed_mate_counts_even_as_an_inaccuracy() -> None:
    inaccuracy = {
        "label": "inaccuracy",
        "is_bad_move": False,
        "win_drop": 6.0,
        "tags": ["missed_mate"],
    }
    moves = make_moves([{**inaccuracy, "game_key": "g1"}, {**inaccuracy, "game_key": "g2"}])

    assert "missed_mates" in ids(tips.tag_tips(make_games(10), moves))


def test_firm_needs_enough_games_and_occurrences() -> None:
    moves = make_moves([blunder(f"g{i}", 20, ["low_clock"]) for i in range(3)])

    [small] = tips.tag_tips(make_games(10), moves)
    [large] = tips.tag_tips(make_games(20), moves)
    assert not small.firm
    assert large.firm


# --- phases --------------------------------------------------------------------


def phase_moves(endgame_accuracy: float) -> pd.DataFrame:
    rows = []
    for i in range(4):
        rows.append({"game_key": f"g{i}", "phase": "opening", "move_accuracy": 95.0})
        rows.append({"game_key": f"g{i}", "phase": "middlegame", "move_accuracy": 93.0})
        rows.append(
            blunder(f"g{i}", 30, [], phase="endgame", move_accuracy=endgame_accuracy, ply=60)
        )
    return make_moves(rows)


def test_weak_phase_counts_only_the_extra_cost() -> None:
    found = tips.phase_tips(make_games(4), phase_moves(endgame_accuracy=60))

    [weak] = [t for t in found if t.id == "weak_endgame"]
    # The other phases have no bad moves, so all of the endgame's cost is "extra".
    assert weak.cost == pytest.approx(4 * 0.3)
    assert "endgame accuracy is 60" in weak.detail
    assert "strong_opening" in ids(found)


def test_no_phase_tip_when_phases_are_close() -> None:
    assert tips.phase_tips(make_games(4), phase_moves(endgame_accuracy=92)) == []


# --- results-based rules ---------------------------------------------------------


def test_conversion_tip() -> None:
    games = make_games(
        5,
        peak_win_chance=[90, 90, 90, 80, 40],
        outcome=["win", "draw", "loss", "loss", "loss"],
        score=[1, 0.5, 0, 0, 0],
    )

    [tip] = tips.conversion_tips(games, make_moves([blunder("g2", 60, [])]))

    assert tip.id == "conversion"
    assert tip.cost == pytest.approx(0.5 + 1 + 1)
    assert "in 4 games but won only 1" in tip.detail
    assert tip.examples[0].game_key == "g1"  # no analysed moves stored for g1 in this test
    assert tip.examples[1].played == "e5"  # g2's costliest move


def test_conversion_strength() -> None:
    games = make_games(6, peak_win_chance=90.0)

    assert ids(tips.conversion_tips(games, make_moves([]))) == ["converts_well"]


def test_bad_opening() -> None:
    families = ["French Defense"] * 4 + ["Italian Game"] * 6
    games = make_games(
        10,
        opening_family=families,
        player_colour="white",
        outcome=["loss"] * 3 + ["draw"] + ["win"] * 6,
        score=[0, 0, 0, 0.5] + [1.0] * 6,
    )

    found = tips.opening_tips(games, make_moves([]))

    assert ids(found) == ["opening_white_French Defense", "opening_strength_white_Italian Game"]
    assert found[0].cost == pytest.approx(4 * (0.5 - 0.125))
    assert found[1].kind == "strength"


def test_time_losses_skip_lost_positions() -> None:
    games = make_games(
        6, outcome=["loss"] * 3 + ["win"] * 3, end_reason=["timeout"] * 3 + ["resigned"] * 3
    )
    moves = make_moves(
        [
            {"game_key": "g0", "win_after": 60.0},
            {"game_key": "g1", "win_after": 45.0},
            {"game_key": "g2", "win_after": 5.0},  # hopelessly lost anyway
        ]
    )

    [tip] = tips.time_loss_tips(games, moves)

    assert tip.games_affected == 2


def test_tilt() -> None:
    # Games 10 minutes apart, in cycles of: loss, loss, then six wins.
    # Overall score 75%; straight after a loss, 50%.
    n = 24
    outcome = ["loss" if i % 8 in (0, 1) else "win" for i in range(n)]
    games = make_games(
        n,
        outcome=outcome,
        score=[0.0 if o == "loss" else 1.0 for o in outcome],
        end_time=[START + timedelta(minutes=10 * i) for i in range(n)],
    )

    [tip] = tips.tilt_tips(games, make_moves([]))

    assert tip.id == "tilt"
    assert "You score 50% in games played within an hour of a loss" in tip.detail
    assert tip.cost == pytest.approx(6 * 0.25)


def test_colour_gap() -> None:
    games = make_games(
        12,
        outcome=["win" if i % 2 == 0 else "loss" for i in range(12)],
        score=[1.0 if i % 2 == 0 else 0.0 for i in range(12)],
    )

    [tip] = tips.colour_tips(games, make_moves([]))

    assert tip.id == "colour_black"
    assert tip.cost == pytest.approx(6 * 1.0 / 2)


# --- ranking ------------------------------------------------------------------


def test_build_tips_ranks_fixes_and_spreads_examples() -> None:
    games = make_games(10)
    shared = [
        blunder(f"g{i}", 40 - i, ["hanging_piece", "missed_punish"], ply=20 + i) for i in range(4)
    ]
    extra = [blunder("g5", 10, ["missed_punish"], ply=50)]
    moves = make_moves(shared + extra)

    found = tips.build_tips(games, moves)

    assert ids(found)[:2] == ["missed_punish", "hanging_pieces"]
    first, second = found[0], found[1]
    assert len(first.examples) == len(second.examples) == 3
    # The second tip shows the one example the first didn't, then repeats.
    first_shown = {(e.game_key, e.ply) for e in first.examples}
    assert (second.examples[0].game_key, second.examples[0].ply) not in first_shown


def test_no_games_no_tips() -> None:
    assert tips.build_tips(make_games(0), make_moves([])) == []


# --- end to end ------------------------------------------------------------------


def test_tips_on_the_sample_database(gold_settings: Settings) -> None:
    from chessguru.app import data

    games = data.load_games(gold_settings.db_path, data.Filters("testplayer"))
    moves = data.load_moves(gold_settings.db_path, "testplayer", list(games["game_key"]))

    found = tips.build_tips(games, moves)

    assert all(t.cost >= 0 for t in found)


def test_cli_tips(gold_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(gold_settings.data_dir))

    result = CliRunner().invoke(app, ["tips", "testplayer"])

    assert result.exit_code == 0, result.stdout
    assert "From your newest 5 games (4 analysed)" in result.stdout


def test_cli_tips_without_data(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESSGURU_DATA_DIR", str(tmp_path))

    result = CliRunner().invoke(app, ["tips", "nobody"])

    assert result.exit_code == 1
