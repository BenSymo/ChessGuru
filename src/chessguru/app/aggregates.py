"""Summaries the dashboard shows, computed from the filtered games and moves.

`games` comes from data.load_games and `moves` from data.load_moves.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PHASES = ["opening", "middlegame", "endgame"]
WINNING = 75.0  # win chance that counts as "winning" (about +3)

TAG_NAMES = {
    "hanging_piece": "Left a piece hanging",
    "missed_fork": "Missed a fork",
    "missed_pin": "Missed a pin",
    "missed_skewer": "Missed a skewer",
    "missed_mate": "Missed a forced mate",
    "allowed_mate": "Walked into mate",
    "missed_punish": "Didn't punish a mistake",
    "low_clock": "Short of time",
    "other": "No simple pattern",
}

END_REASONS = {
    "resigned": "Resigned",
    "checkmated": "Checkmated",
    "timeout": "Ran out of time",
    "abandoned": "Abandoned",
    "agreed": "Draw agreed",
    "repetition": "Repetition",
    "stalemate": "Stalemate",
    "insufficient": "Insufficient material",
    "50move": "50-move rule",
    "timevsinsufficient": "Timeout vs insufficient material",
}


OUTCOME_NAMES = {"win": "Win", "draw": "Draw", "loss": "Loss"}


@dataclass(frozen=True)
class Summary:
    games: int
    wins: int
    draws: int
    losses: int
    score_pct: float | None
    analysed: int
    accuracy: float | None
    blunders_per_game: float | None
    mistakes_per_game: float | None


def summary(games: pd.DataFrame) -> Summary:
    analysed = games[games["is_analysed"]]
    n = len(analysed)
    return Summary(
        games=len(games),
        wins=int((games["outcome"] == "win").sum()),
        draws=int((games["outcome"] == "draw").sum()),
        losses=int((games["outcome"] == "loss").sum()),
        score_pct=float(games["score"].mean()) if len(games) else None,
        analysed=n,
        accuracy=float(analysed["engine_accuracy"].mean()) if n else None,
        blunders_per_game=float(analysed["blunders"].mean()) if n else None,
        mistakes_per_game=float(analysed["mistakes"].mean()) if n else None,
    )


def rating_trend(games: pd.DataFrame) -> pd.DataFrame:
    """Rating after each game, per time class, oldest first."""
    columns = ["time_class", "end_time", "rating"]
    if games.empty:
        return pd.DataFrame(columns=columns)
    trend = games.sort_values("end_time")[["time_class", "end_time", "player_rating"]]
    return trend.rename(columns={"player_rating": "rating"}).reset_index(drop=True)


def phase_stats(moves: pd.DataFrame) -> pd.DataFrame:
    """Accuracy and bad moves per phase. Rates are per game that reached the phase."""
    rows = []
    for phase in PHASES:
        part = moves[moves["phase"] == phase]
        games = part["game_key"].nunique()
        rows.append(
            {
                "phase": phase,
                "games": games,
                "moves": len(part),
                "accuracy": part["move_accuracy"].mean() if len(part) else None,
                "blunders_per_game": (part["label"] == "blunder").sum() / games if games else None,
                "mistakes_per_game": (part["label"] == "mistake").sum() / games if games else None,
                "bad_moves": int(part["is_bad_move"].sum()),
            }
        )
    return pd.DataFrame(rows)


def mistake_types(moves: pd.DataFrame) -> pd.DataFrame:
    """Why bad moves went wrong. A move can count under several reasons."""
    bad = moves[moves["is_bad_move"]]
    if bad.empty:
        return pd.DataFrame(columns=["tag", "name", "moves", "share", "games"])
    tags = bad.assign(tag=bad["tags"].map(lambda t: list(t) if len(t) else ["other"])).explode(
        "tag"
    )
    counts = (
        tags.groupby("tag", as_index=False)
        .agg(moves=("ply", "count"), games=("game_key", "nunique"))
        .sort_values("moves", ascending=False)
    )
    counts["share"] = counts["moves"] / len(bad)
    counts["name"] = counts["tag"].map(lambda t: TAG_NAMES.get(t, t))
    return counts.reset_index(drop=True)[["tag", "name", "moves", "share", "games"]]


def worst_moves(moves: pd.DataFrame, games: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    """The moves that cost the most, with the game they came from."""
    if moves.empty:
        return moves
    worst = moves[moves["is_bad_move"]].nlargest(limit, "win_drop")
    info = games[["game_key", "date_day", "time_control", "player_colour", "opening_family", "url"]]
    return worst.merge(info, on="game_key", how="left")


def opening_table(games: pd.DataFrame, min_games: int = 1) -> pd.DataFrame:
    """Results per opening family and colour, most played first."""
    if games.empty:
        return pd.DataFrame()
    table = games.groupby(["player_colour", "opening_family"], as_index=False).agg(
        games=("game_key", "count"),
        wins=("outcome", lambda s: int((s == "win").sum())),
        draws=("outcome", lambda s: int((s == "draw").sum())),
        losses=("outcome", lambda s: int((s == "loss").sum())),
        score_pct=("score", "mean"),
        accuracy=("engine_accuracy", "mean"),
        last_played=("date_day", "max"),
    )
    table = table[table["games"] >= min_games]
    return table.sort_values(["games", "score_pct"], ascending=[False, True]).reset_index(drop=True)


def time_by_move(moves: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Average seconds per move, by move number, per time class (not daily)."""
    timed = moves.merge(games[["game_key", "time_class"]], on="game_key")
    timed = timed[(timed["time_class"] != "daily") & timed["time_spent_seconds"].notna()]
    if timed.empty:
        return pd.DataFrame(columns=["time_class", "move_number", "seconds", "moves"])
    profile = timed.groupby(["time_class", "move_number"], as_index=False).agg(
        seconds=("time_spent_seconds", "mean"), moves=("ply", "count")
    )
    # Late move numbers are reached in few games, so they are too noisy to show.
    profile = profile[profile["moves"] >= MIN_MOVES_PER_POINT]
    # A 3-move rolling average shows the shape rather than move-to-move noise.
    profile["seconds"] = profile.groupby("time_class")["seconds"].transform(
        lambda s: s.rolling(3, center=True, min_periods=1).mean()
    )
    return profile.reset_index(drop=True)


MIN_MOVES_PER_POINT = 5

CLOCK_BUCKETS = [
    (0.0, 0.1, "Under 10%"),
    (0.1, 0.25, "10 to 25%"),
    (0.25, 0.5, "25 to 50%"),
    (0.5, 10.0, "Over 50%"),
]


def bad_moves_by_clock(moves: pd.DataFrame) -> pd.DataFrame:
    """How often a move is a mistake or blunder, by how much clock was left."""
    timed = moves[moves["clock_fraction_left"].notna()]
    rows = []
    for low, high, name in CLOCK_BUCKETS:
        part = timed[(timed["clock_fraction_left"] >= low) & (timed["clock_fraction_left"] < high)]
        rows.append(
            {
                "clock_left": name,
                "moves": len(part),
                "bad_rate": part["is_bad_move"].mean() if len(part) else None,
            }
        )
    return pd.DataFrame(rows)


def time_losses(games: pd.DataFrame) -> dict[str, int]:
    lost_on_time = games[(games["outcome"] == "loss") & (games["end_reason"] == "timeout")]
    while_winning = lost_on_time[lost_on_time["peak_win_chance"].fillna(0) >= WINNING]
    return {
        "losses": int((games["outcome"] == "loss").sum()),
        "lost_on_time": len(lost_on_time),
        "lost_on_time_while_winning": len(while_winning),
    }


def endings(games: pd.DataFrame) -> pd.DataFrame:
    """How games finish, by outcome."""
    if games.empty:
        return pd.DataFrame(columns=["outcome", "end_reason", "name", "games"])
    table = games.groupby(["outcome", "end_reason"], as_index=False).agg(
        games=("game_key", "count")
    )
    table["name"] = table["end_reason"].map(lambda r: END_REASONS.get(r, r))
    return table.sort_values("games", ascending=False).reset_index(drop=True)


@dataclass(frozen=True)
class Conversion:
    winning_games: int  # analysed games where the player reached a winning position
    won: int
    drawn: int
    lost: int

    @property
    def rate(self) -> float | None:
        return self.won / self.winning_games if self.winning_games else None


def conversion(games: pd.DataFrame) -> Conversion:
    winning = games[games["is_analysed"] & (games["peak_win_chance"].fillna(0) >= WINNING)]
    return Conversion(
        winning_games=len(winning),
        won=int((winning["outcome"] == "win").sum()),
        drawn=int((winning["outcome"] == "draw").sum()),
        lost=int((winning["outcome"] == "loss").sum()),
    )


def endgame_games(moves: pd.DataFrame) -> int:
    return int(moves.loc[moves["phase"] == "endgame", "game_key"].nunique())
