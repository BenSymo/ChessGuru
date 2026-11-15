"""Move scoring, labels, phases and tactic tags, using a fake engine."""

import math

import chess
import pytest

from chessguru.analysis import tactics
from chessguru.analysis.engine import Evaluation, StockfishEvaluator, terminal_evaluation
from chessguru.analysis.game import MoveInput, analyse_game
from chessguru.analysis.phase import count_pieces, phases
from chessguru.analysis.scoring import (
    effective_cp,
    game_accuracy,
    label_for,
    move_accuracy,
    win_chance,
)
from chessguru.config import Settings
from tests.fake_engine import FakeEvaluator


def moves_from(san_moves: str, player_is_white: bool = True) -> list[MoveInput]:
    board = chess.Board()
    out = []
    for ply, san in enumerate(san_moves.split(), start=1):
        move = board.parse_san(san)
        out.append(
            MoveInput(ply, board.fen(), move.uci(), (board.turn == chess.WHITE) == player_is_white)
        )
        board.push(move)
    return out


# --- scoring ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("ev", "expected"),
    [
        (Evaluation(cp=0), 50.0),
        (Evaluation(mate=3), 100.0),
        (Evaluation(mate=-2), 0.0),
        (Evaluation(mate=0), 0.0),
    ],
)
def test_win_chance_fixed_points(ev: Evaluation, expected: float) -> None:
    assert win_chance(ev) == expected


def test_win_chance_is_symmetric_and_capped() -> None:
    assert math.isclose(win_chance(Evaluation(cp=300)) + win_chance(Evaluation(cp=-300)), 100)
    assert 75 < win_chance(Evaluation(cp=300)) < 76
    assert win_chance(Evaluation(cp=5000)) == win_chance(Evaluation(cp=1000))


@pytest.mark.parametrize(
    ("ev", "cp"),
    [(Evaluation(cp=250), 250), (Evaluation(cp=-4000), -1000), (Evaluation(mate=2), 1000)],
)
def test_effective_cp(ev: Evaluation, cp: int) -> None:
    assert effective_cp(ev) == cp


@pytest.mark.parametrize(
    ("drop", "best", "label"),
    [
        (0, True, "best"),
        (2, False, "good"),
        (5, False, "inaccuracy"),
        (9.9, False, "inaccuracy"),
        (10, False, "mistake"),
        (15, True, "blunder"),
        (60, False, "blunder"),
    ],
)
def test_label_for(drop: float, best: bool, label: str) -> None:
    assert label_for(drop, best) == label


def test_move_accuracy() -> None:
    assert move_accuracy(0) == pytest.approx(100, abs=0.01)
    assert move_accuracy(-5) == move_accuracy(0)
    assert 60 < move_accuracy(10) < 64
    assert move_accuracy(100) == 0


def test_game_accuracy_punishes_blunders() -> None:
    assert game_accuracy([]) is None
    assert game_accuracy([100, 100]) == 100
    steady = game_accuracy([80, 80, 80, 80])
    one_blunder = game_accuracy([100, 100, 100, 20])
    assert steady is not None and one_blunder is not None
    assert one_blunder < steady  # same arithmetic mean, but the blunder hurts more


def test_terminal_positions() -> None:
    mated = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")

    assert terminal_evaluation(mated) == Evaluation(mate=0)
    assert terminal_evaluation(stalemate) == Evaluation(cp=0)
    assert terminal_evaluation(chess.Board()) is None


# --- phases ----------------------------------------------------------------


def test_phases_move_forward_only() -> None:
    start = chess.Board()
    late = chess.Board()
    late.fullmove_number = 13
    endgame = chess.Board("4k3/8/8/8/8/8/R7/4K3 w - - 0 40")
    opening_again = chess.Board()

    assert count_pieces(start) == 14
    assert count_pieces(endgame) == 1
    assert phases([start, late, endgame, opening_again]) == [
        "opening",
        "middlegame",
        "endgame",
        "endgame",
    ]


def test_heavy_trades_end_the_opening_early() -> None:
    traded = chess.Board("rnb1k2r/pppppppp/8/8/8/8/PPPPPPPP/RNB1K2R w KQkq - 0 5")

    assert phases([traded]) == ["middlegame"]


# --- tactics ---------------------------------------------------------------


def test_hanging_piece() -> None:
    # Black's knight on e5 is undefended; White's best reply Nxe5 wins it.
    board = chess.Board("4k3/8/8/4n3/8/5N2/8/4K3 w - - 0 1")

    assert tactics.hangs_piece(board, chess.Move.from_uci("f3e5"))
    assert not tactics.hangs_piece(board, chess.Move.from_uci("f3g5"))
    assert not tactics.hangs_piece(board, None)


def test_defended_piece_taken_by_cheaper_piece_still_counts() -> None:
    # Pawn takes a defended knight: still losing material.
    board = chess.Board("4k3/8/5p2/4n3/3P4/8/8/4K3 w - - 0 1")

    assert tactics.hangs_piece(board, chess.Move.from_uci("d4e5"))


def test_pawn_captures_do_not_count_as_hanging() -> None:
    board = chess.Board("4k3/8/8/4p3/8/5N2/8/4K3 w - - 0 1")

    assert not tactics.hangs_piece(board, chess.Move.from_uci("f3e5"))


def test_knight_fork() -> None:
    # Nc7+ forks the king on e8 and the rook on a8.
    board = chess.Board("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1")

    assert tactics.creates_fork(board, chess.Move.from_uci("b5c7"))
    assert not tactics.creates_fork(board, chess.Move.from_uci("b5d4"))


def test_fork_on_a_lost_square_does_not_count() -> None:
    # Nc7+ would fork, but the knight is taken for free by the queen on d8.
    board = chess.Board("r2qk3/8/8/1N6/8/8/8/4K3 w - - 0 1")

    assert not tactics.creates_fork(board, chess.Move.from_uci("b5c7"))


def test_pin() -> None:
    # Bb5 pins the knight on c6 to the king on e8.
    board = chess.Board("4k3/8/2n5/8/8/8/8/2B1K3 w - - 0 1")
    board = chess.Board("4k3/3p4/2n5/8/8/8/8/3BK3 w - - 0 1")
    board = chess.Board("4k3/8/2n5/8/8/8/3B4/4K3 w - - 0 1")
    bishop = chess.Board("4k3/8/2n5/8/B7/8/8/4K3 w - - 0 1")

    assert tactics.creates_pin(
        chess.Board("4k3/8/2n5/8/8/8/8/3BK3 w - - 0 1"), chess.Move.from_uci("d1a4")
    )
    assert not tactics.creates_pin(bishop, chess.Move.from_uci("a4b3"))
    assert board is not None


def test_skewer() -> None:
    # Ra1+ attacks the king on a5, with the queen behind it on a8.
    board = chess.Board("q7/8/8/k7/8/8/8/1R2K3 w - - 0 1")

    assert tactics.creates_skewer(board, chess.Move.from_uci("b1a1"))
    assert not tactics.creates_skewer(board, chess.Move.from_uci("b1b2"))


# --- whole games -------------------------------------------------------------


def test_scholars_mate_from_blacks_side() -> None:
    # Black (the player) plays 3...Nf6?? and gets mated.
    moves = moves_from("e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#", player_is_white=False)

    result = analyse_game(moves, FakeEvaluator())

    nf6 = result.moves[5]
    qxf7 = result.moves[6]
    assert nf6.label == "blunder"
    assert "allowed_mate" in nf6.tags
    assert nf6.win_after == 0
    assert qxf7.label == "best"
    assert qxf7.mate_after == 0  # this move gave checkmate
    assert qxf7.win_after == 100
    assert result.player_accuracy is not None
    assert result.player_accuracy < 90  # one blunder in four moves pulls it down hard


def test_missed_mate() -> None:
    # White could mate with Qxf7# but plays Qh4 instead.
    moves = moves_from("e4 e5 Bc4 Nc6 Qh5 Nf6 Qh4")

    result = analyse_game(moves, FakeEvaluator())

    qh4 = result.moves[6]
    assert "missed_mate" in qh4.tags
    assert qh4.best_move_san == "Qxf7#"


def test_each_position_is_evaluated_once() -> None:
    engine = FakeEvaluator()

    analyse_game(moves_from("e4 e5 Nf3"), engine)

    assert engine.calls == 4  # 3 positions before each move + the final position


def test_empty_game() -> None:
    result = analyse_game([], FakeEvaluator())

    assert result.moves == []
    assert result.player_accuracy is None


STOCKFISH = Settings().resolve_stockfish()


@pytest.mark.skipif(STOCKFISH is None, reason="Stockfish is not installed")
def test_real_stockfish() -> None:
    assert STOCKFISH is not None
    engine = StockfishEvaluator(STOCKFISH, depth=8)
    try:
        start = engine.evaluate(chess.Board())
        mate_in_one = engine.evaluate(chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"))
    finally:
        engine.close()

    assert start.cp is not None and -100 < start.cp < 100
    assert mate_in_one.mate == 1
    assert mate_in_one.best_move == "a1a8"
