"""Spot simple tactical patterns, to say *why* a move was a mistake.

These are deliberately simple checks on the engine's best move. They catch
the common cases (a piece left hanging, a missed fork) rather than every
tactic a strong player would name.
"""

from __future__ import annotations

import chess

VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def _value(piece: chess.Piece) -> int:
    return VALUES[piece.piece_type]


def hangs_piece(board_after: chess.Board, reply: chess.Move | None) -> bool:
    """After our move, can the opponent's best reply win a piece for free (or cheaply)?

    `board_after` is the position after our move, with the opponent to move.
    """
    if reply is None or not board_after.is_capture(reply) or board_after.is_en_passant(reply):
        return False
    target = board_after.piece_at(reply.to_square)
    attacker = board_after.piece_at(reply.from_square)
    if target is None or attacker is None or target.piece_type == chess.PAWN:
        return False
    undefended = not board_after.is_attacked_by(target.color, reply.to_square)
    return undefended or _value(target) > _value(attacker)


def creates_fork(board: chess.Board, move: chess.Move) -> bool:
    """Does `move` attack two or more valuable enemy pieces at once?"""
    after = board.copy(stack=False)
    after.push(move)
    piece = after.piece_at(move.to_square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    enemy = not piece.color
    # A fork with a piece that is simply lost doesn't count.
    if after.is_attacked_by(enemy, move.to_square) and not after.is_attacked_by(
        piece.color, move.to_square
    ):
        return False
    targets = 0
    for square in after.attacks(move.to_square):
        target = after.piece_at(square)
        if target is None or target.color != enemy:
            continue
        if (
            target.piece_type == chess.KING
            or _value(target) > _value(piece)
            or (_value(target) >= 3 and not after.is_attacked_by(enemy, square))
        ):
            targets += 1
    return targets >= 2


def _pinned_pieces(board: chess.Board, colour: chess.Color) -> set[chess.Square]:
    return {
        square
        for square in chess.SQUARES
        if (piece := board.piece_at(square))
        and piece.color == colour
        and piece.piece_type not in (chess.PAWN, chess.KING)
        and board.is_pinned(colour, square)
    }


def creates_pin(board: chess.Board, move: chess.Move) -> bool:
    """Does `move` pin an enemy piece (not a pawn) to its king?"""
    enemy = not board.turn
    before = _pinned_pieces(board, enemy)
    after = board.copy(stack=False)
    after.push(move)
    return bool(_pinned_pieces(after, enemy) - before)


def creates_skewer(board: chess.Board, move: chess.Move) -> bool:
    """Does `move` attack a valuable piece with a less valuable enemy piece behind it?"""
    after = board.copy(stack=False)
    after.push(move)
    piece = after.piece_at(move.to_square)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    enemy = not piece.color
    origin = move.to_square
    for square in after.attacks(origin):
        front = after.piece_at(square)
        if front is None or front.color != enemy or _value(front) < 5:
            continue
        step_file = _sign(chess.square_file(square) - chess.square_file(origin))
        step_rank = _sign(chess.square_rank(square) - chess.square_rank(origin))
        file, rank = chess.square_file(square) + step_file, chess.square_rank(square) + step_rank
        while 0 <= file < 8 and 0 <= rank < 8:
            behind = after.piece_at(chess.square(file, rank))
            if behind is not None:
                if behind.color == enemy and 3 <= _value(behind) < _value(front):
                    return True
                break
            file, rank = file + step_file, rank + step_rank
    return False


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)
