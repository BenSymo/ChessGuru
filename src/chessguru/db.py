"""The local DuckDB database and its housekeeping tables."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from chessguru.quality.checks import Rejected

# Bump this when the silver tables change shape. Silver can always be rebuilt
# from bronze, so an older version just drops silver and parses again.
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS quarantine (
    username        VARCHAR NOT NULL,
    source_file     VARCHAR NOT NULL,
    game_url        VARCHAR,
    reason          VARCHAR NOT NULL,
    quarantined_at  TIMESTAMPTZ NOT NULL
);
-- Added in milestone 3: which pipeline step set the game aside.
ALTER TABLE quarantine ADD COLUMN IF NOT EXISTS step VARCHAR DEFAULT 'check';

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       VARCHAR NOT NULL,
    step         VARCHAR NOT NULL,
    username     VARCHAR NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ NOT NULL,
    status       VARCHAR NOT NULL,
    details      JSON
);

-- Silver: one row per game, from the analysed player's side of the board.
CREATE TABLE IF NOT EXISTS silver_games (
    username           VARCHAR NOT NULL,
    game_uuid          VARCHAR NOT NULL,
    url                VARCHAR NOT NULL,
    end_time           TIMESTAMPTZ NOT NULL,
    time_class         VARCHAR NOT NULL,
    time_control       VARCHAR NOT NULL,
    base_seconds       INTEGER,
    increment_seconds  INTEGER,
    rated              BOOLEAN NOT NULL,
    player_colour      VARCHAR NOT NULL,
    player_rating      INTEGER NOT NULL,
    opponent_username  VARCHAR NOT NULL,
    opponent_key       VARCHAR NOT NULL,
    opponent_rating    INTEGER NOT NULL,
    player_result      VARCHAR NOT NULL,
    outcome            VARCHAR NOT NULL,
    end_reason         VARCHAR NOT NULL,
    eco_code           VARCHAR,
    opening_name       VARCHAR,
    opening_family     VARCHAR,
    player_accuracy    DOUBLE,
    opponent_accuracy  DOUBLE,
    plies              INTEGER NOT NULL,
    pgn                VARCHAR NOT NULL,
    parsed_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (username, game_uuid)
);

-- Silver: one row per move (ply) in each game.
CREATE TABLE IF NOT EXISTS silver_moves (
    username            VARCHAR NOT NULL,
    game_uuid           VARCHAR NOT NULL,
    ply                 INTEGER NOT NULL,
    move_number         INTEGER NOT NULL,
    colour              VARCHAR NOT NULL,
    is_player_move      BOOLEAN NOT NULL,
    san                 VARCHAR NOT NULL,
    uci                 VARCHAR NOT NULL,
    piece               VARCHAR NOT NULL,
    is_capture          BOOLEAN NOT NULL,
    is_check            BOOLEAN NOT NULL,
    is_castle           BOOLEAN NOT NULL,
    is_promotion        BOOLEAN NOT NULL,
    fen_before          VARCHAR NOT NULL,
    clock_seconds       DOUBLE,
    time_spent_seconds  DOUBLE,
    PRIMARY KEY (username, game_uuid, ply)
);

-- Silver: Stockfish's verdict on every move, from the mover's point of view.
CREATE TABLE IF NOT EXISTS silver_move_evals (
    username       VARCHAR NOT NULL,
    game_uuid      VARCHAR NOT NULL,
    ply            INTEGER NOT NULL,
    phase          VARCHAR NOT NULL,
    cp_before      INTEGER NOT NULL,
    cp_after       INTEGER NOT NULL,
    mate_before    INTEGER,
    mate_after     INTEGER,
    win_before     DOUBLE NOT NULL,
    win_after      DOUBLE NOT NULL,
    win_drop       DOUBLE NOT NULL,
    cp_loss        INTEGER NOT NULL,
    accuracy       DOUBLE NOT NULL,
    label          VARCHAR NOT NULL,
    best_move_uci  VARCHAR,
    best_move_san  VARCHAR,
    tags           VARCHAR[] NOT NULL,
    PRIMARY KEY (username, game_uuid, ply)
);

-- Silver: which games have been analysed, how deeply, and the engine accuracy.
CREATE TABLE IF NOT EXISTS silver_game_analysis (
    username           VARCHAR NOT NULL,
    game_uuid          VARCHAR NOT NULL,
    engine_depth       INTEGER NOT NULL,
    player_accuracy    DOUBLE,
    opponent_accuracy  DOUBLE,
    analysed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (username, game_uuid)
);
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    _migrate(conn)
    conn.execute(SCHEMA)
    return conn


def _migrate(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] is not None else None
    if current == SCHEMA_VERSION:
        return
    if current is not None or _table_exists(conn, "silver_games"):
        # Older silver tables: drop them; the next parse rebuilds them from bronze.
        for table in ("silver_game_analysis", "silver_move_evals", "silver_moves", "silver_games"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version VALUES (?)", [SCHEMA_VERSION])


def _table_exists(conn: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()
    return bool(row and row[0])


def replace_quarantine(
    conn: duckdb.DuckDBPyConnection,
    username: str,
    rejected: Iterable[Rejected],
    when: datetime,
    step: str = "check",
) -> None:
    """Swap in this step's quarantined games, so re-running never duplicates rows."""
    rows = [(username, r.source, r.game_url, r.reason, when, step) for r in rejected]
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM quarantine WHERE username = ? AND step = ?", [username, step])
        if rows:
            conn.executemany(
                "INSERT INTO quarantine "
                "(username, source_file, game_url, reason, quarantined_at, step) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


@contextmanager
def logged_run(
    conn: duckdb.DuckDBPyConnection,
    step: str,
    username: str,
    started: datetime | None = None,
) -> Iterator[dict[str, Any]]:
    """Record each pipeline step, whether it worked or failed.

    The caller can add to the yielded dict; it is saved as the run's details.
    Pass `started` when the work began before the database could be opened.
    """
    details: dict[str, Any] = {}
    started = started or datetime.now(UTC)
    status = "failed"
    try:
        yield details
        status = "succeeded"
    except BaseException as exc:
        details["error"] = str(exc)
        raise
    finally:
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                uuid.uuid4().hex,
                step,
                username,
                started,
                datetime.now(UTC),
                status,
                json.dumps(details, default=str),
            ],
        )
