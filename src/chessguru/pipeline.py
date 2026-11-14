"""Pipeline steps. The CLI (and later Airflow) call these same functions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from chessguru.analysis.engine import EngineError, Evaluator, StockfishEvaluator
from chessguru.analysis.store import AnalyseSummary, Progress, analyse_games
from chessguru.api.client import ChessComClient
from chessguru.api.contracts import Game
from chessguru.config import Settings
from chessguru.db import connect, logged_run, replace_quarantine
from chessguru.governance.hashing import load_key, make_hasher
from chessguru.ingest.bronze import BronzeStore
from chessguru.ingest.fetch import FetchSummary, fetch_recent_games
from chessguru.parse.games import ParsedGame, ParseError, parse_game
from chessguru.parse.silver import stored_game_ids, write_games
from chessguru.quality.checks import CheckReport, Rejected, check_games
from chessguru.transform.dbt import DbtError, DbtResult, run_dbt


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


@dataclass
class ParseSummary:
    parsed: int = 0
    already_stored: int = 0
    rejected: list[Rejected] = field(default_factory=list)


def parse(
    settings: Settings, username: str, games: Sequence[Game], now: datetime | None = None
) -> ParseSummary:
    """Turn checked games into silver rows. Games already in silver are skipped."""
    now = now or datetime.now(UTC)
    name = username.lower()
    summary = ParseSummary()
    hash_name = make_hasher(load_key(settings))
    conn = connect(settings.db_path)
    try:
        with logged_run(conn, "parse", name) as details:
            stored = stored_game_ids(conn, name)
            parsed: list[ParsedGame] = []
            for game in games:
                if game.uuid in stored:
                    summary.already_stored += 1
                    continue
                try:
                    parsed.append(parse_game(game, name, hash_name))
                except ParseError as exc:
                    summary.rejected.append(Rejected("silver", str(exc), game.url))
            write_games(conn, parsed, now)
            replace_quarantine(conn, name, summary.rejected, now, step="parse")
            summary.parsed = len(parsed)
            details.update(
                parsed=summary.parsed,
                already_stored=summary.already_stored,
                quarantined=len(summary.rejected),
            )
        return summary
    finally:
        conn.close()


def build(settings: Settings, username: str = "all") -> DbtResult:
    """Build and test the gold layer with dbt."""
    started = datetime.now(UTC)
    conn = connect(settings.db_path)  # makes sure the silver tables exist
    conn.close()
    result: DbtResult | None = None
    error: Exception | None = None
    try:
        result = run_dbt(settings, "build")
    except DbtError as exc:
        error = exc
    # DuckDB allows one writer at a time, so log only after dbt has finished.
    conn = connect(settings.db_path)
    try:
        with logged_run(conn, "build", username, started=started) as details:
            if error:
                raise error
            assert result is not None
            details.update(passed=result.passed, failures=result.failures)
            if result.failures:
                raise DbtError("; ".join(result.failures))
        return result
    finally:
        conn.close()


def analyse(
    settings: Settings,
    username: str,
    max_games: int | None = None,
    make_evaluator: Callable[[], Evaluator] | None = None,
    workers: int | None = None,
    progress: Progress | None = None,
    now: datetime | None = None,
    only: list[str] | None = None,
) -> AnalyseSummary:
    """Run Stockfish over the newest games. Games already analysed are skipped.

    `only` limits the choice to these game IDs (the dashboard uses this).
    """
    now = now or datetime.now(UTC)
    name = username.lower()
    if make_evaluator is None:
        path = settings.resolve_stockfish()
        if path is None:
            raise EngineError(
                "Stockfish was not found. Install it, or set CHESSGURU_STOCKFISH_PATH."
            )
        depth = settings.engine_depth

        def make_evaluator() -> Evaluator:
            return StockfishEvaluator(path, depth)

    conn = connect(settings.db_path)
    try:
        with logged_run(conn, "analyse", name) as details:
            summary = analyse_games(
                conn,
                name,
                max_games or settings.max_games,
                settings.engine_depth,
                make_evaluator,
                now,
                workers=workers,
                progress=progress,
                only=only,
            )
            details.update(
                selected=summary.selected,
                analysed=summary.analysed,
                already_done=summary.already_done,
                depth=settings.engine_depth,
            )
        return summary
    finally:
        conn.close()
