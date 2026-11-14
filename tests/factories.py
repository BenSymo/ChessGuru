"""Builders for fake chess.com data. All names are made up."""

from __future__ import annotations

import json
from typing import Any

from chessguru.api.contracts import STANDARD_START

SCHOLARS_MATE = """[Event "Live Chess"]
[Site "Chess.com"]
[White "TestPlayer"]
[Black "opponent1"]
[Result "1-0"]
[TimeControl "600"]

1. e4 {[%clk 0:09:58]} 1... e5 {[%clk 0:09:57]} 2. Bc4 {[%clk 0:09:55]} 2... Nc6 {[%clk 0:09:50]}
3. Qh5 {[%clk 0:09:50]} 3... Nf6 {[%clk 0:09:40]} 4. Qxf7# {[%clk 0:09:45]} 1-0
"""


def make_game(n: int = 1, **overrides: Any) -> dict[str, Any]:
    """A game in chess.com's format. TestPlayer is White unless overridden."""
    game: dict[str, Any] = {
        "url": f"https://www.chess.com/game/live/{1000 + n}",
        "uuid": f"uuid-{n}",
        "pgn": SCHOLARS_MATE,
        "time_control": "600",
        "time_class": "rapid",
        "end_time": 1793000000 + n * 1000,
        "rated": True,
        "rules": "chess",
        "initial_setup": STANDARD_START,
        "fen": "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4",
        "tcn": "ignored",
        "white": {"username": "TestPlayer", "rating": 1200, "result": "win", "uuid": "a"},
        "black": {"username": f"opponent{n}", "rating": 1180, "result": "checkmated", "uuid": "b"},
        "accuracies": {"white": 92.1, "black": 40.3},
        "eco": "https://www.chess.com/openings/Bishops-Opening",
    }
    game.update(overrides)
    return game


def month_json(*games: dict[str, Any]) -> bytes:
    return json.dumps({"games": list(games)}).encode()


def archives_json(username: str, *months: str) -> dict[str, Any]:
    base = f"https://api.chess.com/pub/player/{username}/games"
    return {"archives": [f"{base}/{m.replace('-', '/')}" for m in months]}
