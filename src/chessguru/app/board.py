"""Draw chess positions as SVG for the dashboard."""

from __future__ import annotations

import chess
import chess.svg

PLAYED_BAD = "#d03b3bcc"  # critical red, slightly see-through
PLAYED = "#2a78d6cc"
BEST = "#0ca30ccc"  # good green
BOARD_COLOURS = {"square light": "#e8e4d8", "square dark": "#8aa1b4"}


def position_svg(
    fen: str,
    played: str | None = None,
    best: str | None = None,
    bad: bool = False,
    flipped: bool = False,
    size: int = 360,
) -> str:
    """The position before a move, with the played move (and the better one) as arrows.

    `played` and `best` are UCI moves.
    """
    board = chess.Board(fen)
    arrows = []
    if best and best != played:
        move = chess.Move.from_uci(best)
        arrows.append(chess.svg.Arrow(move.from_square, move.to_square, color=BEST))
    if played:
        move = chess.Move.from_uci(played)
        colour = PLAYED_BAD if bad else PLAYED
        arrows.append(chess.svg.Arrow(move.from_square, move.to_square, color=colour))
    return chess.svg.board(
        board,
        arrows=arrows,
        flipped=flipped,
        size=size,
        coordinates=True,
        colors=BOARD_COLOURS,
    )


def san_to_uci(fen: str, san: str | None) -> str | None:
    if not san:
        return None
    try:
        return chess.Board(fen).parse_san(san).uci()
    except ValueError:
        return None
