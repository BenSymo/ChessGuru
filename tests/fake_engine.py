"""A tiny, predictable stand-in for Stockfish, used in tests.

It scores positions by material only and suggests the move that mates or
captures the most valuable piece. Good enough to test the plumbing.
"""

from __future__ import annotations

import chess

from chessguru.analysis.engine import Evaluation, terminal_evaluation
from chessguru.analysis.tactics import VALUES


def material(board: chess.Board, colour: chess.Color) -> int:
    return sum(
        VALUES[piece.piece_type]
        for piece in board.piece_map().values()
        if piece.color == colour and piece.piece_type != chess.KING
    )


class FakeEvaluator:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def evaluate(self, board: chess.Board) -> Evaluation:
        self.calls += 1
        done = terminal_evaluation(board)
        if done:
            return done
        moves = sorted(board.legal_moves, key=lambda m: m.uci())
        for move in moves:
            board.push(move)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                return Evaluation(mate=1, best_move=move.uci())

        def gain(move: chess.Move) -> int:
            target = board.piece_at(move.to_square)
            return VALUES[target.piece_type] if target else 0

        best = max(moves, key=gain)
        cp = 100 * (material(board, board.turn) - material(board, not board.turn))
        return Evaluation(cp=cp, best_move=best.uci())

    def close(self) -> None:
        self.closed = True
