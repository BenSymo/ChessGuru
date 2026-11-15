"""Turn a checked chess.com game into silver rows: one game row, one row per move.

Pure functions with no database access, so they are easy to test.
"""

from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

import chess
import chess.pgn

from chessguru.api.contracts import Game

Outcome = Literal["win", "draw", "loss"]
Colour = Literal["white", "black"]

DRAW_RESULTS = frozenset(
    {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
)
# Words that end an opening's family name, e.g. "Sicilian Defense", "Italian Game".
_FAMILY_ENDINGS = frozenset(
    {"Defense", "Defence", "Opening", "Attack", "Gambit", "Game", "System", "Countergambit"}
)
_TIME_CONTROL_RE = re.compile(r"^(\d+)(?:\+(\d+))?$")


class ParseError(Exception):
    """The game's PGN could not be turned into moves."""


@dataclass(frozen=True)
class GameRow:
    username: str
    game_uuid: str
    url: str
    end_time: datetime
    time_class: str
    time_control: str
    base_seconds: int | None
    increment_seconds: int | None
    rated: bool
    player_colour: Colour
    player_rating: int
    player_result: str
    outcome: Outcome
    end_reason: str
    eco_code: str | None
    opening_name: str | None
    opening_family: str | None
    plies: int


@dataclass(frozen=True)
class MoveRow:
    username: str
    game_uuid: str
    ply: int
    move_number: int
    colour: Colour
    is_player_move: bool
    san: str
    uci: str
    piece: str
    fen_before: str
    clock_seconds: float | None
    time_spent_seconds: float | None


@dataclass(frozen=True)
class ParsedGame:
    game: GameRow
    moves: list[MoveRow]


def as_dicts(rows: list[GameRow] | list[MoveRow]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]


def parse_time_control(time_control: str) -> tuple[int | None, int | None]:
    """'600' -> (600, 0); '180+2' -> (180, 2); daily '1/86400' -> (None, None)."""
    match = _TIME_CONTROL_RE.match(time_control)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2) or 0)


def outcome_of(result: str) -> Outcome:
    if result == "win":
        return "win"
    if result in DRAW_RESULTS:
        return "draw"
    return "loss"


def opening_from_url(url: str | None) -> tuple[str | None, str | None]:
    """Opening name and family from a chess.com opening URL.

    '.../openings/Sicilian-Defense-Najdorf-Variation-6.Be3'
      -> ('Sicilian Defense Najdorf Variation', 'Sicilian Defense')
    """
    if not url or "/openings/" not in url:
        return None, None
    words: list[str] = []
    for word in url.rsplit("/openings/", 1)[1].split("-"):
        if not word or word[0].isdigit() or word.startswith("..."):
            break  # the move list starts here
        words.append(word)
    if not words:
        return None, None
    family = words
    for i, word in enumerate(words):
        if word in _FAMILY_ENDINGS:
            family = words[: i + 1]
            break
    return " ".join(words), " ".join(family)


def parse_game(game: Game, username: str) -> ParsedGame:
    """Build the silver rows for one game, from `username`'s side of the board.

    Nothing about the opponent is kept except their result, so no one else's
    personal data is stored.
    """
    colour = game.colour_of(username)
    if colour is None:
        raise ParseError(f"{username} did not play in this game")
    player, opponent = (game.white, game.black) if colour == "white" else (game.black, game.white)

    pgn_game = chess.pgn.read_game(io.StringIO(game.pgn))
    if pgn_game is None or pgn_game.errors:
        raise ParseError("PGN could not be parsed")

    base, increment = parse_time_control(game.time_control)
    track_time = game.time_class != "daily" and base is not None
    last_clock: dict[bool, float | None] = {chess.WHITE: base, chess.BLACK: base}

    board = pgn_game.board()
    moves: list[MoveRow] = []
    for ply, node in enumerate(pgn_game.mainline(), start=1):
        move = node.move
        piece = board.piece_at(move.from_square)
        if piece is None:  # pragma: no cover - python-chess already rejects these
            raise ParseError(f"No piece to move at ply {ply}")
        side = board.turn
        clock = node.clock()

        spent: float | None = None
        previous = last_clock[side]
        if track_time and clock is not None and previous is not None:
            spent = max(0.0, round(previous + (increment or 0) - clock, 1))
        last_clock[side] = clock

        moves.append(
            MoveRow(
                username=username,
                game_uuid=game.uuid,
                ply=ply,
                move_number=board.fullmove_number,
                colour="white" if side == chess.WHITE else "black",
                is_player_move=(side == chess.WHITE) == (colour == "white"),
                san=board.san(move),
                uci=move.uci(),
                piece=piece.symbol().upper(),
                fen_before=board.fen(),
                clock_seconds=clock,
                time_spent_seconds=spent,
            )
        )
        board.push(move)

    if not moves:
        raise ParseError("no moves played")

    opening_name, opening_family = opening_from_url(pgn_game.headers.get("ECOUrl") or game.eco)
    outcome = outcome_of(player.result)
    return ParsedGame(
        game=GameRow(
            username=username,
            game_uuid=game.uuid,
            url=game.url,
            end_time=game.end_time,
            time_class=game.time_class,
            time_control=game.time_control,
            base_seconds=base,
            increment_seconds=increment,
            rated=game.rated,
            player_colour=colour,
            player_rating=player.rating,
            player_result=player.result,
            outcome=outcome,
            # How the game ended: the loser's code says it best (resigned, timeout, ...).
            end_reason=opponent.result if outcome == "win" else player.result,
            eco_code=pgn_game.headers.get("ECO") or None,
            opening_name=opening_name,
            opening_family=opening_family,
            plies=len(moves),
        ),
        moves=moves,
    )
