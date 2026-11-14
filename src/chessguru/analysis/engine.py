"""Position evaluation. Stockfish in real use; a fake in tests."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chess
import chess.engine


class EngineError(Exception):
    """Stockfish is missing or stopped working."""


@dataclass(frozen=True)
class Evaluation:
    """A position's score from the side to move's point of view.

    Exactly one of `cp` (centipawns) or `mate` (moves to mate; negative means
    being mated, 0 means already checkmated) is set.
    """

    cp: int | None = None
    mate: int | None = None
    best_move: str | None = None  # UCI


class Evaluator(Protocol):
    def evaluate(self, board: chess.Board) -> Evaluation: ...

    def close(self) -> None: ...


def terminal_evaluation(board: chess.Board) -> Evaluation | None:
    """Score finished positions without asking the engine."""
    if board.is_checkmate():
        return Evaluation(mate=0)
    if board.is_stalemate() or board.is_insufficient_material():
        return Evaluation(cp=0)
    return None


class StockfishEvaluator:
    def __init__(self, path: Path, depth: int, hash_mb: int = 64) -> None:
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(str(path))
            self._engine.configure({"Threads": 1, "Hash": hash_mb})
        except (OSError, chess.engine.EngineError) as exc:
            raise EngineError(f"Could not start Stockfish at {path}: {exc}") from exc
        self._limit = chess.engine.Limit(depth=depth)

    def evaluate(self, board: chess.Board) -> Evaluation:
        done = terminal_evaluation(board)
        if done:
            return done
        try:
            info = self._engine.analyse(board, self._limit)
        except chess.engine.EngineError as exc:  # pragma: no cover - engine crash
            raise EngineError(f"Stockfish failed: {exc}") from exc
        score = info["score"].pov(board.turn)
        pv = info.get("pv") or []
        best = pv[0].uci() if pv else None
        if score.is_mate():
            return Evaluation(mate=score.mate(), best_move=best)
        return Evaluation(cp=score.score(), best_move=best)

    def close(self) -> None:
        with contextlib.suppress(chess.engine.EngineError, OSError):
            self._engine.quit()
