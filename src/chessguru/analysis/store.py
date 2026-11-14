"""Pick games to analyse, run the engine on them, and save the results."""

from __future__ import annotations

import os
import queue
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime

import duckdb
import pyarrow as pa

from chessguru.analysis.engine import Evaluator
from chessguru.analysis.game import GameAnalysis, MoveInput, analyse_game

Progress = Callable[[int, int], None]


@dataclass
class AnalyseSummary:
    selected: int = 0
    analysed: int = 0
    already_done: int = 0


def default_workers() -> int:
    """Leave one core free so the computer stays usable."""
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def games_to_analyse(
    conn: duckdb.DuckDBPyConnection,
    username: str,
    max_games: int,
    depth: int,
    only: list[str] | None = None,
) -> tuple[list[str], int]:
    """The newest `max_games` games, minus those already analysed at this depth or deeper.

    With `only`, choose from just those games (e.g. the ones shown in the dashboard).
    Returns (games still to do, how many of the chosen games are already done).
    """
    rows = conn.execute(
        """
        select g.game_uuid, a.engine_depth >= ? as done
        from silver_games g
        left join silver_game_analysis a using (username, game_uuid)
        where g.username = ? and (? is null or list_contains(?, g.game_uuid))
        order by g.end_time desc, g.game_uuid
        limit ?
        """,
        [depth, username, only, only, max_games],
    ).fetchall()
    todo = [uuid for uuid, done in rows if not done]
    return todo, len(rows) - len(todo)


def load_moves(conn: duckdb.DuckDBPyConnection, username: str, game_uuid: str) -> list[MoveInput]:
    rows = conn.execute(
        "select ply, fen_before, uci, is_player_move from silver_moves "
        "where username = ? and game_uuid = ? order by ply",
        [username, game_uuid],
    ).fetchall()
    return [MoveInput(*row) for row in rows]


def write_analysis(
    conn: duckdb.DuckDBPyConnection,
    username: str,
    game_uuid: str,
    analysis: GameAnalysis,
    depth: int,
    when: datetime,
) -> None:
    moves = pa.Table.from_pylist(
        [{"username": username, "game_uuid": game_uuid, **asdict(m)} for m in analysis.moves],
        schema=_MOVE_SCHEMA,
    )
    conn.execute("BEGIN")
    try:
        conn.register("new_evals", moves)
        key = [username, game_uuid]
        conn.execute("DELETE FROM silver_move_evals WHERE username = ? AND game_uuid = ?", key)
        conn.execute("DELETE FROM silver_game_analysis WHERE username = ? AND game_uuid = ?", key)
        conn.execute("INSERT INTO silver_move_evals BY NAME SELECT * FROM new_evals")
        conn.execute(
            "INSERT INTO silver_game_analysis VALUES (?, ?, ?, ?, ?, ?)",
            [*key, depth, analysis.player_accuracy, analysis.opponent_accuracy, when],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.unregister("new_evals")


_MOVE_SCHEMA = pa.schema(
    [
        ("username", pa.string()),
        ("game_uuid", pa.string()),
        ("ply", pa.int32()),
        ("phase", pa.string()),
        ("cp_before", pa.int32()),
        ("cp_after", pa.int32()),
        ("mate_before", pa.int32()),
        ("mate_after", pa.int32()),
        ("win_before", pa.float64()),
        ("win_after", pa.float64()),
        ("win_drop", pa.float64()),
        ("cp_loss", pa.int32()),
        ("accuracy", pa.float64()),
        ("label", pa.string()),
        ("best_move_uci", pa.string()),
        ("best_move_san", pa.string()),
        ("tags", pa.list_(pa.string())),
    ]
)


def analyse_games(
    conn: duckdb.DuckDBPyConnection,
    username: str,
    max_games: int,
    depth: int,
    make_evaluator: Callable[[], Evaluator],
    now: datetime,
    workers: int | None = None,
    progress: Progress | None = None,
    only: list[str] | None = None,
) -> AnalyseSummary:
    """Analyse the newest games in parallel, saving each game as soon as it is done.

    Stopping part-way loses nothing: finished games are already saved, and the
    next run carries on with the rest.
    """
    todo, done = games_to_analyse(conn, username, max_games, depth, only)
    summary = AnalyseSummary(selected=len(todo) + done, already_done=done)
    if not todo:
        return summary

    inputs = {uuid: load_moves(conn, username, uuid) for uuid in todo}
    count = min(workers or default_workers(), len(todo))
    pool_of_engines: queue.Queue[Evaluator] = queue.Queue()
    engines = []
    try:
        for _ in range(count):
            engine = make_evaluator()
            engines.append(engine)
            pool_of_engines.put(engine)

        def work(uuid: str) -> tuple[str, GameAnalysis]:
            engine = pool_of_engines.get()
            try:
                return uuid, analyse_game(inputs[uuid], engine)
            finally:
                pool_of_engines.put(engine)

        pool = ThreadPoolExecutor(max_workers=count)
        try:
            futures = [pool.submit(work, uuid) for uuid in todo]
            for future in as_completed(futures):
                uuid, analysis = future.result()
                write_analysis(conn, username, uuid, analysis, depth, now)
                summary.analysed += 1
                if progress:
                    progress(summary.analysed, len(todo))
        finally:
            # If a game fails, don't wait for the rest of the queue before reporting it.
            pool.shutdown(wait=True, cancel_futures=True)
    finally:
        for engine in engines:
            engine.close()
    return summary
