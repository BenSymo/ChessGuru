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

SCHEMA = """
CREATE TABLE IF NOT EXISTS quarantine (
    username        VARCHAR NOT NULL,
    source_file     VARCHAR NOT NULL,
    game_url        VARCHAR,
    reason          VARCHAR NOT NULL,
    quarantined_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       VARCHAR NOT NULL,
    step         VARCHAR NOT NULL,
    username     VARCHAR NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ NOT NULL,
    status       VARCHAR NOT NULL,
    details      JSON
);
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    conn.execute(SCHEMA)
    return conn


def replace_quarantine(
    conn: duckdb.DuckDBPyConnection,
    username: str,
    rejected: Iterable[Rejected],
    when: datetime,
) -> None:
    """Swap in this run's quarantined games, so re-running never duplicates rows."""
    rows = [(username, r.source, r.game_url, r.reason, when) for r in rejected]
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM quarantine WHERE username = ?", [username])
        if rows:
            conn.executemany("INSERT INTO quarantine VALUES (?, ?, ?, ?, ?)", rows)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


@contextmanager
def logged_run(
    conn: duckdb.DuckDBPyConnection, step: str, username: str
) -> Iterator[dict[str, Any]]:
    """Record each pipeline step, whether it worked or failed.

    The caller can add to the yielded dict; it is saved as the run's details.
    """
    details: dict[str, Any] = {}
    started = datetime.now(UTC)
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
