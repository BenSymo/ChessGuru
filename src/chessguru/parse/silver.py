"""Read and write the silver tables."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import duckdb
import pyarrow as pa

from chessguru.parse.games import ParsedGame, as_dicts


def stored_game_ids(conn: duckdb.DuckDBPyConnection, username: str) -> set[str]:
    rows = conn.execute(
        "SELECT game_uuid FROM silver_games WHERE username = ?", [username]
    ).fetchall()
    return {row[0] for row in rows}


def write_games(
    conn: duckdb.DuckDBPyConnection, parsed: Sequence[ParsedGame], when: datetime
) -> None:
    """Insert games and their moves. Re-writing a game replaces it, never duplicates it."""
    if not parsed:
        return
    games = pa.Table.from_pylist(
        [{**row, "parsed_at": when} for row in as_dicts([p.game for p in parsed])]
    )
    moves = pa.Table.from_pylist(as_dicts([m for p in parsed for m in p.moves]))
    keys = pa.Table.from_pylist(
        [{"username": p.game.username, "game_uuid": p.game.game_uuid} for p in parsed]
    )

    conn.execute("BEGIN")
    try:
        conn.register("new_games", games)
        conn.register("new_moves", moves)
        conn.register("new_keys", keys)
        for table in ("silver_moves", "silver_games"):
            conn.execute(
                f"DELETE FROM {table} WHERE (username, game_uuid) IN "
                "(SELECT (username, game_uuid) FROM new_keys)"
            )
        conn.execute("INSERT INTO silver_games BY NAME SELECT * FROM new_games")
        conn.execute("INSERT INTO silver_moves BY NAME SELECT * FROM new_moves")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        for name in ("new_games", "new_moves", "new_keys"):
            conn.unregister(name)
