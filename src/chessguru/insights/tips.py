"""Tip rules.

Each rule looks at your games (and analysed moves), checks a pattern against a
limit, and, if it fires, produces a Tip with:

- `cost`: roughly how many games' worth of points the problem cost you. For bad
  moves this is the drop in your chance of winning, added up per game and
  capped at one game each. For results (openings, tilt) it is points below
  what you'd otherwise expect.
- `based_on`: how many games the tip is based on, so you can tell a firm
  pattern from an early hint.
- up to 3 example positions (or games) from your own play.

Tips are ranked by cost, so the first one is what to fix first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

import pandas as pd

WINNING = 75.0  # win chance that counts as "winning" (about +3)
MIN_GAMES_AFFECTED = 2  # a pattern must show up in at least this many games
FIRM_GAMES_AFFECTED = 3  # ...and this many (in FIRM_SAMPLE+ games) to be "firm"
FIRM_SAMPLE = 15
TILT_WINDOW_MINUTES = 60

Kind = Literal["fix", "strength"]


@dataclass(frozen=True)
class Example:
    game_key: str
    url: str
    date_day: date | None
    ply: int | None = None
    fen: str | None = None
    played: str | None = None
    best: str | None = None
    win_drop: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class Tip:
    id: str
    area: str
    title: str
    detail: str
    advice: str
    cost: float
    based_on: int
    games_affected: int
    kind: Kind = "fix"
    examples: list[Example] = field(default_factory=list)

    @property
    def firm(self) -> bool:
        """A firm pattern rather than an early hint."""
        return self.games_affected >= FIRM_GAMES_AFFECTED and self.based_on >= FIRM_SAMPLE


# --- helpers -------------------------------------------------------------------


def _cost(bad_moves: pd.DataFrame) -> float:
    """Win chance thrown away, added up per game and capped at one game each."""
    if bad_moves.empty:
        return 0.0
    per_game = bad_moves.groupby("game_key")["win_drop"].sum() / 100
    return float(per_game.clip(upper=1.0).sum())


EXAMPLES_SHOWN = 3
EXAMPLE_CANDIDATES = 8  # gathered per tip, so repeats across tips can be skipped


def _move_examples(
    bad_moves: pd.DataFrame, games: pd.DataFrame, limit: int = EXAMPLE_CANDIDATES
) -> list[Example]:
    worst = bad_moves.nlargest(limit, "win_drop").merge(
        games[["game_key", "url", "date_day"]], on="game_key", how="left"
    )
    return [
        Example(
            game_key=row.game_key,
            url=row.url,
            date_day=row.date_day,
            ply=int(row.ply),
            fen=row.fen_before,
            played=row.san,
            best=row.best_move_san,
            win_drop=float(row.win_drop),
        )
        for row in worst.itertuples()
    ]


def _game_examples(
    chosen: pd.DataFrame, moves: pd.DataFrame, note: Callable[[pd.Series], str]
) -> list[Example]:
    """One example per game: the move where it went most wrong, if analysed."""
    examples = []
    for _, game in chosen.head(EXAMPLE_CANDIDATES).iterrows():
        game_moves = moves[moves["game_key"] == game["game_key"]]
        worst = game_moves.nlargest(1, "win_drop") if not game_moves.empty else game_moves
        if not worst.empty and worst.iloc[0]["win_drop"] > 0:
            move = worst.iloc[0]
            examples.append(
                Example(
                    game_key=game["game_key"],
                    url=game["url"],
                    date_day=game["date_day"],
                    ply=int(move["ply"]),
                    fen=move["fen_before"],
                    played=move["san"],
                    best=move["best_move_san"],
                    win_drop=float(move["win_drop"]),
                    note=note(game),
                )
            )
        else:
            examples.append(
                Example(game["game_key"], game["url"], game["date_day"], note=note(game))
            )
    return examples


def _bad(moves: pd.DataFrame) -> pd.DataFrame:
    return moves[moves["is_bad_move"]]


def _has_any_tag(moves: pd.DataFrame, tags: set[str]) -> pd.Series:
    return moves["tags"].map(lambda t: bool(tags.intersection(t)))


def _pct(value: float) -> str:
    return f"{value:.0%}"


# --- rules -----------------------------------------------------------------------


@dataclass(frozen=True)
class TagRule:
    id: str
    tags: frozenset[str]
    area: str
    title: str
    advice: str


TAG_RULES = [
    TagRule(
        "hanging_pieces",
        frozenset({"hanging_piece"}),
        "Tactics",
        "You leave pieces hanging",
        "Before every move, check what it leaves undefended: look at every capture your "
        "opponent could make in reply.",
    ),
    TagRule(
        "missed_tactics",
        frozenset({"missed_fork", "missed_pin", "missed_skewer"}),
        "Tactics",
        "You miss forks, pins and skewers",
        "Do 10–15 minutes of tactics puzzles a day. Look for two targets at once: "
        "a fork, or pieces lined up on one file or diagonal.",
    ),
    TagRule(
        "missed_mates",
        frozenset({"missed_mate"}),
        "Tactics",
        "You miss forced mates",
        "When you're attacking, look at every check before anything else, then captures, "
        "then threats.",
    ),
    TagRule(
        "allowed_mates",
        frozenset({"allowed_mate"}),
        "King safety",
        "You walk into mating attacks",
        "Before each move, look at your opponent's checks and which of your king's "
        "defenders your move takes away.",
    ),
    TagRule(
        "missed_punish",
        frozenset({"missed_punish"}),
        "Tactics",
        "You don't punish your opponent's mistakes",
        "When your opponent's move looks odd, slow down: ask what it leaves undefended "
        "and whether you can win something.",
    ),
    TagRule(
        "time_trouble",
        frozenset({"low_clock"}),
        "Time",
        "You blunder when short of time",
        "Spend less time in the opening so you have time for the critical moments. "
        "Aim to still have a third of your clock at move 20.",
    ),
]


def tag_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    analysed = int(games["is_analysed"].sum())
    tips = []
    for rule in TAG_RULES:
        hits = moves[_has_any_tag(moves, set(rule.tags))]
        if rule.id != "missed_mates":  # a missed mate counts even as an inaccuracy
            hits = hits[hits["is_bad_move"]]
        affected = hits["game_key"].nunique()
        if affected < MIN_GAMES_AFFECTED:
            continue
        tips.append(
            Tip(
                id=rule.id,
                area=rule.area,
                title=rule.title,
                detail=f"{len(hits)} costly moves in {affected} of your {analysed} analysed games.",
                advice=rule.advice,
                cost=_cost(hits),
                based_on=analysed,
                games_affected=affected,
                examples=_move_examples(hits, games),
            )
        )
    return tips


PHASE_ADVICE = {
    "opening": (
        "Your openings cost you",
        "Learn the first 6–8 moves of your main openings, and the plans behind them, "
        "so you reach the middlegame on equal terms.",
    ),
    "middlegame": (
        "The middlegame is your weak spot",
        "When there's no obvious plan, look for checks, captures and threats first, "
        "then improve your worst-placed piece.",
    ),
    "endgame": (
        "Your endgames are weaker than the rest of your game",
        "Study the basic endgames: active king, rook endgames, and king-and-pawn endings.",
    ),
}
PHASE_GAP = 3.0  # accuracy points between a phase and the others to count


def phase_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    stats = []
    for phase in PHASE_ADVICE:
        part = moves[moves["phase"] == phase]
        n_games = part["game_key"].nunique()
        if n_games >= FIRM_GAMES_AFFECTED:
            stats.append((phase, float(part["move_accuracy"].mean()), n_games, part))
    if len(stats) < 2:
        return []

    tips = []
    weakest = min(stats, key=lambda s: s[1])
    others = [s[1] for s in stats if s[0] != weakest[0]]
    gap = sum(others) / len(others) - weakest[1]
    if gap >= PHASE_GAP:
        phase, accuracy, n_games, part = weakest
        bad = _bad(part)
        title, advice = PHASE_ADVICE[phase]
        # Only count what this phase loses *beyond* your usual rate elsewhere, so the
        # tip doesn't simply repeat the other tips' costly moves.
        rest = moves[moves["phase"] != phase]
        usual_per_move = _cost(_bad(rest)) / len(rest) if len(rest) else 0.0
        excess = max(0.0, _cost(bad) - usual_per_move * len(part))
        tips.append(
            Tip(
                id=f"weak_{phase}",
                area=phase.title(),
                title=title,
                detail=f"Your {phase} accuracy is {accuracy:.0f}, {gap:.0f} points below "
                "the rest of your game.",
                advice=advice,
                cost=excess,
                based_on=n_games,
                games_affected=bad["game_key"].nunique(),
                examples=_move_examples(bad, games),
            )
        )

    strongest = max(stats, key=lambda s: s[1])
    others = [s[1] for s in stats if s[0] != strongest[0]]
    lead = strongest[1] - sum(others) / len(others)
    if lead >= PHASE_GAP:
        phase, accuracy, n_games, _ = strongest
        tips.append(
            Tip(
                id=f"strong_{phase}",
                area=phase.title(),
                title=f"Your {phase} is a strength",
                detail=f"Your {phase} accuracy is {accuracy:.0f}, {lead:.0f} points above the "
                "rest of your game.",
                advice="Steer towards it: positions that suit you are worth aiming for.",
                cost=0.0,
                based_on=n_games,
                games_affected=n_games,
                kind="strength",
            )
        )
    return tips


def conversion_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    analysed = games[games["is_analysed"]]
    winning = analysed[analysed["peak_win_chance"].fillna(0) >= WINNING]
    if len(winning) < FIRM_GAMES_AFFECTED:
        return []
    slipped = winning[winning["outcome"] != "win"]
    won = len(winning) - len(slipped)
    if len(slipped) >= MIN_GAMES_AFFECTED:
        return [
            Tip(
                id="conversion",
                area="Converting",
                title="You let winning positions slip",
                detail=f"You reached a winning position (about +3) in {len(winning)} games "
                f"but won only {won}.",
                advice="When you're ahead, simplify: trade pieces (not pawns), take away your "
                "opponent's counterplay, and don't rush.",
                cost=float((1 - slipped["score"]).sum()),
                based_on=len(winning),
                games_affected=len(slipped),
                examples=_game_examples(
                    slipped,
                    moves,
                    lambda g: f"Was {g['peak_win_chance']:.0f}% to win, {g['outcome']}",
                ),
            )
        ]
    if won / len(winning) >= 0.9 and len(winning) >= 5:
        return [
            Tip(
                id="converts_well",
                area="Converting",
                title="You convert winning positions well",
                detail=f"You won {won} of the {len(winning)} games where you reached a "
                "winning position.",
                advice="Keep it up: the points you earn, you keep.",
                cost=0.0,
                based_on=len(winning),
                games_affected=won,
                kind="strength",
            )
        ]
    return []


def opening_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    min_games = max(3, round(0.1 * len(games)))
    table = games.groupby(["player_colour", "opening_family"]).agg(
        games=("game_key", "count"), score=("score", "mean")
    )
    table = table[(table["games"] >= min_games) & (table.index.get_level_values(1) != "Unknown")]
    tips = []
    for (colour, family), row in (
        table[table["score"] < 0.4].sort_values("score").head(2).iterrows()
    ):
        chosen = games[(games["player_colour"] == colour) & (games["opening_family"] == family)]
        losses = chosen[chosen["outcome"] != "win"]
        tips.append(
            Tip(
                id=f"opening_{colour}_{family}",
                area="Openings",
                title=f"The {family} isn't working for you as {colour.title()}",
                detail=f"You scored {_pct(row['score'])} in {int(row['games'])} games.",
                advice="Play through a model game in this line, or switch to an opening whose "
                "ideas you understand better.",
                cost=float(row["games"] * (0.5 - row["score"])),
                based_on=int(row["games"]),
                games_affected=len(losses),
                examples=_game_examples(losses, moves, lambda g: str(g["outcome"]).title()),
            )
        )
    best = table[table["score"] >= 0.65].sort_values(["score", "games"], ascending=False).head(1)
    for (colour, family), row in best.iterrows():
        tips.append(
            Tip(
                id=f"opening_strength_{colour}_{family}",
                area="Openings",
                title=f"The {family} works well for you as {colour.title()}",
                detail=f"You scored {_pct(row['score'])} in {int(row['games'])} games.",
                advice="Keep playing it, and learn it a little deeper.",
                cost=0.0,
                based_on=int(row["games"]),
                games_affected=int(row["games"]),
                kind="strength",
            )
        )
    return tips


def time_loss_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    timeouts = games[(games["outcome"] == "loss") & (games["end_reason"] == "timeout")]
    if not moves.empty and len(timeouts):
        last = moves.sort_values("ply").groupby("game_key")["win_after"].last()
        playable = timeouts["game_key"].map(last).fillna(50) >= 40
        timeouts = timeouts[playable.to_numpy()]
    if len(timeouts) < MIN_GAMES_AFFECTED:
        return []
    return [
        Tip(
            id="time_losses",
            area="Time",
            title="You lose on time in playable positions",
            detail=f"{len(timeouts)} of your {len(games)} games were lost on time while the "
            "position was still playable.",
            advice="Keep a time buffer. When your clock gets low, play safe, simple moves "
            "quickly rather than looking for the best one.",
            cost=float(len(timeouts)),
            based_on=len(games),
            games_affected=len(timeouts),
            examples=_game_examples(timeouts, moves, lambda g: "Lost on time"),
        )
    ]


def tilt_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    ordered = games.sort_values("end_time").reset_index(drop=True)
    if len(ordered) < 10:
        return []
    gap = ordered["end_time"].diff().dt.total_seconds() / 60
    after_loss = (ordered["outcome"].shift() == "loss") & (gap <= TILT_WINDOW_MINUTES)
    after = ordered[after_loss]
    if len(after) < 5:
        return []
    overall, then = float(ordered["score"].mean()), float(after["score"].mean())
    if overall - then < 0.15:
        return []
    return [
        Tip(
            id="tilt",
            area="Mindset",
            title="Your results drop straight after a loss",
            detail=f"You score {_pct(then)} in games played within an hour of a loss, "
            f"against {_pct(overall)} overall.",
            advice="After a loss, take a 5–10 minute break before the next game, and stop for "
            "the day after two losses in a row.",
            cost=len(after) * (overall - then),
            based_on=len(after),
            games_affected=int((after["outcome"] != "win").sum()),
        )
    ]


def colour_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    by_colour = games.groupby("player_colour")["score"].agg(["mean", "count"])
    if len(by_colour) < 2 or (by_colour["count"] < 5).any():
        return []
    weak = str(by_colour["mean"].idxmin())
    strong = str(by_colour["mean"].idxmax())
    gap = float(by_colour.loc[strong, "mean"] - by_colour.loc[weak, "mean"])
    if gap < 0.2:
        return []
    n_weak = int(by_colour.loc[weak, "count"])
    return [
        Tip(
            id=f"colour_{weak}",
            area="Openings",
            title=f"You score much less as {weak.title()}",
            detail=f"{_pct(by_colour.loc[weak, 'mean'])} as {weak.title()} against "
            f"{_pct(by_colour.loc[strong, 'mean'])} as {strong.title()}.",
            advice=f"Look at your openings as {weak.title()}: choose solid lines whose plans "
            "you understand, and review your losses with that colour.",
            cost=n_weak * gap / 2,
            based_on=n_weak,
            games_affected=int((games[games["player_colour"] == weak]["outcome"] != "win").sum()),
        )
    ]


RULES = [
    tag_tips,
    phase_tips,
    conversion_tips,
    opening_tips,
    time_loss_tips,
    tilt_tips,
    colour_tips,
]


def build_tips(games: pd.DataFrame, moves: pd.DataFrame) -> list[Tip]:
    """Every tip that fires, fixes first (biggest cost first), then strengths."""
    if games.empty:
        return []
    tips = [tip for rule in RULES for tip in rule(games, moves)]
    fixes = sorted((t for t in tips if t.kind == "fix" and t.cost > 0), key=lambda t: -t.cost)
    strengths = sorted((t for t in tips if t.kind == "strength"), key=lambda t: -t.based_on)
    return _spread_examples(fixes) + strengths


def _spread_examples(tips: list[Tip]) -> list[Tip]:
    """Keep 3 examples per tip, preferring ones not already shown by a higher tip."""
    seen: set[tuple[str, int | None]] = set()
    result = []
    for tip in tips:
        fresh = [e for e in tip.examples if (e.game_key, e.ply) not in seen]
        repeats = [e for e in tip.examples if (e.game_key, e.ply) in seen]
        chosen = (fresh + repeats)[:EXAMPLES_SHOWN]
        seen.update((e.game_key, e.ply) for e in chosen)
        result.append(replace(tip, examples=chosen))
    return result
