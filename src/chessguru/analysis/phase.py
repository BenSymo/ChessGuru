"""Opening, middlegame or endgame for each position."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import chess

Phase = Literal["opening", "middlegame", "endgame"]

OPENING_LAST_MOVE = 12  # the opening ends after this move number at the latest
MIDDLEGAME_PIECES = 10  # ...or once this few pieces (not pawns or kings) remain
ENDGAME_PIECES = 6  # the endgame starts once this few pieces remain


def count_pieces(board: chess.Board) -> int:
    """Knights, bishops, rooks and queens on the board, both sides."""
    return sum(
        len(board.pieces(piece_type, colour))
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for colour in (chess.WHITE, chess.BLACK)
    )


def phases(boards: Sequence[chess.Board]) -> list[Phase]:
    """The phase of each position. Phases only move forward, never back."""
    result: list[Phase] = []
    current: Phase = "opening"
    for board in boards:
        pieces = count_pieces(board)
        if current == "opening" and (
            board.fullmove_number > OPENING_LAST_MOVE or pieces <= MIDDLEGAME_PIECES
        ):
            current = "middlegame"
        if pieces <= ENDGAME_PIECES:
            current = "endgame"
        result.append(current)
    return result
