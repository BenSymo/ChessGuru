"""Read the gold tables for the dashboard. No Streamlit here, so it is easy to test."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd


class DataUnavailable(Exception):
    """The database is missing, not built yet, or busy."""


@dataclass(frozen=True)
class Filters:
    username: str
    time_classes: tuple[str, ...] = ()  # empty = all
    last_n: int | None = None  # newest N games after the other filters
    colour: str | None = None  # "white", "black" or None for both
    rated_only: bool = False


GAMES_SQL = """
select
    f.game_key, f.game_uuid, f.username, f.end_time, f.date_day, f.time_class,
    tc.label as time_control, f.rated, f.player_colour, f.outcome, f.score, f.end_reason,
    f.player_rating, f.plies, f.is_analysed, f.engine_accuracy, f.blunders, f.mistakes,
    f.inaccuracies, f.peak_win_chance, f.failed_to_convert, f.url, o.opening_family
from gold.fact_game f
join gold.dim_time_control tc using (time_control_key)
join gold.dim_opening o using (opening_key)
where f.username = ?
order by f.end_time desc, f.game_uuid
"""

MOVES_SQL = """
select
    m.game_key, m.ply, m.move_number, m.san, m.piece, m.phase, m.label, m.is_bad_move,
    m.win_before, m.win_after, m.win_drop, m.move_accuracy, m.best_move_san,
    m.tags, m.clock_seconds, m.time_spent_seconds, m.clock_fraction_left, m.fen_before
from gold.fact_move m
where m.username = ? and m.is_player_move and m.is_analysed
    and list_contains(?, m.game_key)
order by m.game_key, m.ply
"""


def _connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    if not db_path.exists():
        raise DataUnavailable("No database yet. Fetch your games first.")
    try:
        return duckdb.connect(str(db_path), read_only=True)
    except duckdb.IOException as exc:
        raise DataUnavailable(
            "The database is busy (another ChessGuru command is running). Try again shortly."
        ) from exc


def _query(db_path: Path, sql: str, params: list[object] | None = None) -> pd.DataFrame:
    conn = _connect(db_path)
    try:
        return conn.execute(sql, params or []).df()
    except duckdb.CatalogException as exc:
        raise DataUnavailable("The gold tables aren't built yet. Run an update first.") from exc
    finally:
        conn.close()


def usernames(db_path: Path) -> list[str]:
    try:
        frame = _query(db_path, "select distinct username from gold.fact_game order by 1")
    except DataUnavailable:
        return []
    return [str(name) for name in frame["username"]]


def load_games(db_path: Path, filters: Filters) -> pd.DataFrame:
    """The filtered games, newest first."""
    games = _query(db_path, GAMES_SQL, [filters.username])
    if filters.time_classes:
        games = games[games["time_class"].isin(filters.time_classes)]
    if filters.colour:
        games = games[games["player_colour"] == filters.colour]
    if filters.rated_only:
        games = games[games["rated"]]
    if filters.last_n:
        games = games.head(filters.last_n)
    return games.reset_index(drop=True)


def load_moves(db_path: Path, username: str, game_keys: list[str]) -> pd.DataFrame:
    """The player's own analysed moves in these games."""
    if not game_keys:
        return pd.DataFrame(columns=_MOVE_COLUMNS)
    return _none_for_missing(_query(db_path, MOVES_SQL, [username, game_keys]))


_MOVE_COLUMNS = [
    "game_key", "ply", "move_number", "san", "piece", "phase", "label", "is_bad_move",
    "win_before", "win_after", "win_drop", "move_accuracy", "best_move_san",
    "tags", "clock_seconds", "time_spent_seconds", "clock_fraction_left", "fen_before",
]  # fmt: skip


GAME_MOVES_SQL = """
select
    m.ply, m.move_number, m.colour, m.is_player_move, m.san, m.uci, m.fen_before,
    m.clock_seconds, m.time_spent_seconds, m.is_analysed, m.phase, m.label, m.is_bad_move,
    m.win_before, m.win_after, m.win_drop, m.best_move_san, m.best_move_uci, m.tags
from gold.fact_move m
where m.username = ? and m.game_key = ?
order by m.ply
"""


def load_game_moves(db_path: Path, username: str, game_key: str) -> pd.DataFrame:
    """Every move of one game, both sides, with engine verdicts where analysed."""
    return _none_for_missing(_query(db_path, GAME_MOVES_SQL, [username, game_key]))


def _none_for_missing(moves: pd.DataFrame) -> pd.DataFrame:
    """Missing moves come back from DuckDB as NaN, which counts as true in `if` checks
    and prints as "nan". Use None instead, so "no better move" reads as no move."""
    for column in ("best_move_san", "best_move_uci"):
        if column in moves:
            moves[column] = moves[column].astype(object).where(moves[column].notna(), None)
    return moves


def health(db_path: Path) -> dict[str, pd.DataFrame]:
    """Pipeline runs, quarantine and row counts for the Data Health page."""
    queries = {
        "runs": """
            select step, username, status, started_at,
                   round(epoch(finished_at - started_at), 1) as seconds, details
            from pipeline_runs order by started_at desc limit 50
        """,
        "quarantine": """
            select username, step, reason, count(*) as games
            from quarantine group by all order by games desc
        """,
        "counts": """
            select 'Silver games' as layer, count(*) as rows from silver_games
            union all select 'Silver moves', count(*) from silver_moves
            union all select 'Analysed games', count(*) from silver_game_analysis
            union all select 'Analysed moves', count(*) from silver_move_evals
            union all select 'Quarantined games', count(*) from quarantine
        """,
    }
    conn = _connect(db_path)
    try:
        return {name: conn.execute(sql).df() for name, sql in queries.items()}
    finally:
        conn.close()
