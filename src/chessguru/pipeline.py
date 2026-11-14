"""Pipeline steps. The CLI (and later Airflow) call these same functions."""

from __future__ import annotations

from datetime import UTC, datetime

from chessguru.api.client import ChessComClient
from chessguru.config import Settings
from chessguru.db import connect, logged_run, replace_quarantine
from chessguru.ingest.bronze import BronzeStore
from chessguru.ingest.fetch import FetchSummary, fetch_recent_games
from chessguru.quality.checks import CheckReport, check_games


def fetch(
    settings: Settings,
    username: str,
    max_games: int | None = None,
    client: ChessComClient | None = None,
    now: datetime | None = None,
) -> FetchSummary:
    """Download recent games for `username` into the bronze layer."""
    now = now or datetime.now(UTC)
    limit = max_games or settings.max_games
    store = BronzeStore(settings.bronze_dir)
    owns_client = client is None
    client = client or ChessComClient(settings.user_agent)
    conn = connect(settings.db_path)
    try:
        with logged_run(conn, "fetch", username) as details:
            summary = fetch_recent_games(client, store, username, limit, now.date())
            details.update(
                downloaded=[m.key for m in summary.downloaded],
                cached=[m.key for m in summary.cached],
                games_found=summary.games_found,
            )
        return summary
    finally:
        conn.close()
        if owns_client:
            client.close()


def check(settings: Settings, username: str, now: datetime | None = None) -> CheckReport:
    """Run data quality checks on every stored month and refresh the quarantine table."""
    now = now or datetime.now(UTC)
    store = BronzeStore(settings.bronze_dir)
    months = [(f"{m.key}.json", store.read(username, m)) for m in store.months(username)]
    conn = connect(settings.db_path)
    try:
        with logged_run(conn, "check", username) as details:
            report = check_games(username, months, now)
            replace_quarantine(conn, username.lower(), report.rejected, now)
            details.update(
                valid=len(report.valid),
                quarantined=len(report.rejected),
                warnings=report.warnings,
            )
        return report
    finally:
        conn.close()
