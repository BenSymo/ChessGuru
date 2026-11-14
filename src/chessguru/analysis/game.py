"""Analyse one game: score every position, then label and tag every move."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import chess

from chessguru.analysis import tactics
from chessguru.analysis.engine import Evaluation, Evaluator
from chessguru.analysis.phase import Phase, phases
from chessguru.analysis.scoring import (
    Label,
    effective_cp,
    game_accuracy,
    label_for,
    move_accuracy,
    win_chance,
)

BAD_LABELS = frozenset({"mistake", "blunder"})


@dataclass(frozen=True)
class MoveInput:
    ply: int
    fen_before: str
    uci: str
    is_player_move: bool


@dataclass(frozen=True)
class MoveEval:
    """One move, scored from the point of view of the side that played it."""

    ply: int
    phase: Phase
    cp_before: int
    cp_after: int
    mate_before: int | None
    mate_after: int | None
    win_before: float
    win_after: float
    win_drop: float
    cp_loss: int
    accuracy: float
    label: Label
    best_move_uci: str | None
    best_move_san: str | None
    tags: list[str]


@dataclass(frozen=True)
class GameAnalysis:
    moves: list[MoveEval]
    player_accuracy: float | None
    opponent_accuracy: float | None


def _flip(ev: Evaluation) -> Evaluation:
    """The same score, seen from the other side.

    `mate=0` means the side to move is checkmated; seen from the side that just
    moved, that is a won position, so it is scored like a mate in 1.
    """
    if ev.mate == 0:
        return Evaluation(mate=1)
    if ev.mate is not None:
        return Evaluation(mate=-ev.mate, best_move=ev.best_move)
    return Evaluation(cp=-(ev.cp or 0), best_move=ev.best_move)


def _parse_move(board: chess.Board, uci: str | None) -> chess.Move | None:
    if not uci:
        return None
    move = chess.Move.from_uci(uci)
    return move if move in board.legal_moves else None


def analyse_game(moves: Sequence[MoveInput], evaluator: Evaluator) -> GameAnalysis:
    if not moves:
        return GameAnalysis([], None, None)

    boards = [chess.Board(m.fen_before) for m in moves]
    final = boards[-1].copy(stack=False)
    final.push_uci(moves[-1].uci)
    positions = [*boards, final]
    evals = [evaluator.evaluate(board) for board in positions]
    position_phases = phases(boards)

    results: list[MoveEval] = []
    for i, move_in in enumerate(moves):
        board = boards[i]
        played = chess.Move.from_uci(move_in.uci)
        before = evals[i]
        after = _flip(evals[i + 1])  # back to the mover's point of view
        delivered_mate = evals[i + 1].mate == 0
        win_before, win_after = win_chance(before), win_chance(after)
        drop = max(0.0, win_before - win_after)
        best = _parse_move(board, before.best_move)
        label = label_for(drop, played_best=best == played)

        tags = _tags(
            board=board,
            board_after=positions[i + 1],
            played=played,
            best=best,
            before=before,
            after=after,
            reply=_parse_move(positions[i + 1], evals[i + 1].best_move),
            label=label,
            previous_label=results[-1].label if results else None,
        )
        results.append(
            MoveEval(
                ply=move_in.ply,
                phase=position_phases[i],
                cp_before=effective_cp(before),
                cp_after=effective_cp(after),
                mate_before=before.mate,
                mate_after=0 if delivered_mate else after.mate,
                win_before=round(win_before, 2),
                win_after=round(win_after, 2),
                win_drop=round(drop, 2),
                cp_loss=max(0, effective_cp(before) - effective_cp(after)),
                accuracy=round(move_accuracy(drop), 2),
                label=label,
                best_move_uci=best.uci() if best else None,
                best_move_san=board.san(best) if best else None,
                tags=tags,
            )
        )

    player = [r.accuracy for r, m in zip(results, moves, strict=True) if m.is_player_move]
    opponent = [r.accuracy for r, m in zip(results, moves, strict=True) if not m.is_player_move]
    return GameAnalysis(results, _round(game_accuracy(player)), _round(game_accuracy(opponent)))


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _tags(
    *,
    board: chess.Board,
    board_after: chess.Board,
    played: chess.Move,
    best: chess.Move | None,
    before: Evaluation,
    after: Evaluation,
    reply: chess.Move | None,
    label: Label,
    previous_label: Label | None,
) -> list[str]:
    """Why a move went wrong. Only bad moves (and missed mates) get tags."""
    tags: list[str] = []
    had_mate = before.mate is not None and before.mate > 0
    still_mating = after.mate is not None and after.mate > 0
    if had_mate and not still_mating and label != "best":
        tags.append("missed_mate")
    if label not in BAD_LABELS:
        return tags

    already_lost = before.mate is not None and before.mate < 0
    if after.mate is not None and after.mate < 0 and not already_lost:
        tags.append("allowed_mate")
    if tactics.hangs_piece(board_after, reply):
        tags.append("hanging_piece")
    if best is not None and best != played:
        if tactics.creates_fork(board, best) and not tactics.creates_fork(board, played):
            tags.append("missed_fork")
        if tactics.creates_pin(board, best) and not tactics.creates_pin(board, played):
            tags.append("missed_pin")
        if tactics.creates_skewer(board, best) and not tactics.creates_skewer(board, played):
            tags.append("missed_skewer")
    if previous_label in BAD_LABELS:
        tags.append("missed_punish")  # the opponent had just gone wrong, and we didn't profit
    return tags
