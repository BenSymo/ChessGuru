"""Turn engine scores into winning chances, move labels and accuracy.

The formulas follow Lichess, so the numbers are comparable to what players
see there.
"""

from __future__ import annotations

import math
from typing import Literal

from chessguru.analysis.engine import Evaluation

Label = Literal["best", "good", "inaccuracy", "mistake", "blunder"]

CP_CAP = 1000
# Drop in win chance (percentage points) for each label. Lichess uses 0.1 / 0.2 /
# 0.3 on a -1..1 scale, which is 5 / 10 / 15 points on a 0..100 scale.
INACCURACY = 5.0
MISTAKE = 10.0
BLUNDER = 15.0


def effective_cp(ev: Evaluation) -> int:
    """Centipawns, with mates counted as +/- the cap."""
    if ev.mate is not None:
        return CP_CAP if ev.mate > 0 else -CP_CAP
    return max(-CP_CAP, min(CP_CAP, ev.cp or 0))


def win_chance(ev: Evaluation) -> float:
    """Chance of winning (0-100) for the side to move."""
    if ev.mate is not None:
        return 100.0 if ev.mate > 0 else 0.0
    cp = max(-CP_CAP, min(CP_CAP, ev.cp or 0))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def label_for(drop: float, played_best: bool) -> Label:
    if drop >= BLUNDER:
        return "blunder"
    if drop >= MISTAKE:
        return "mistake"
    if drop >= INACCURACY:
        return "inaccuracy"
    return "best" if played_best else "good"


def move_accuracy(drop: float) -> float:
    """Lichess's accuracy for one move, from the drop in win chance."""
    raw = 103.1668 * math.exp(-0.04354 * max(0.0, drop)) - 3.1669
    return max(0.0, min(100.0, raw))


def game_accuracy(move_accuracies: list[float]) -> float | None:
    """Average of the arithmetic and harmonic means, so a few blunders count fully.

    This is a simplified version of Lichess's method (no volatility weighting).
    """
    if not move_accuracies:
        return None
    mean = sum(move_accuracies) / len(move_accuracies)
    harmonic = len(move_accuracies) / sum(1 / max(a, 1.0) for a in move_accuracies)
    return (mean + harmonic) / 2
