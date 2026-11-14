"""Data quality checks on raw games, before they reach the silver layer.

Each check has an action when it fails:
- quarantine: set the game aside with a reason, keep going
- warn:       keep the game, but report the problem
- stop:       something is badly wrong (e.g. chess.com changed its format), so halt
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import ValidationError

from chessguru.api.contracts import STANDARD_START, Game

# Stop if more than this share of games break the contract: the API has probably changed.
CONTRACT_FAILURE_LIMIT = 0.5
# Warn if the newest game is older than this.
STALE_AFTER = timedelta(days=30)


class DataContractError(Exception):
    """Too many games broke the data contract to trust this batch."""


@dataclass(frozen=True)
class Rejected:
    source: str
    reason: str
    game_url: str | None = None


@dataclass
class CheckReport:
    valid: list[Game] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.rejected)


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error["loc"]) or "game"
    return f"breaks data contract: {where}: {error['msg']}"


def check_games(
    username: str,
    months: Iterable[tuple[str, bytes]],
    now: datetime,
) -> CheckReport:
    """Run every check over raw month files given as (source name, raw bytes)."""
    report = CheckReport()
    seen: set[str] = set()
    contract_failures = 0

    for source, raw in months:
        # Completeness: the file itself must be readable.
        try:
            payload = json.loads(raw)
            items = payload["games"]
            if not isinstance(items, list):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            report.rejected.append(Rejected(source, "month file is not readable JSON"))
            continue

        for item in items:
            url = item.get("url") if isinstance(item, dict) else None

            # Validity: the game matches the data contract.
            try:
                game = Game.model_validate(item)
            except ValidationError as exc:
                contract_failures += 1
                report.rejected.append(Rejected(source, _first_error(exc), url))
                continue

            # Uniqueness: each game appears once.
            if game.uuid in seen:
                report.rejected.append(Rejected(source, "duplicate game", game.url))
                continue
            seen.add(game.uuid)

            # Validity: only standard chess can be analysed.
            if game.rules != "chess":
                reason = f"variant '{game.rules}' is not supported"
                report.rejected.append(Rejected(source, reason, game.url))
                continue
            if game.initial_setup != STANDARD_START:
                report.rejected.append(Rejected(source, "custom start position", game.url))
                continue

            # Validity: the player actually played in this game.
            if game.colour_of(username) is None:
                reason = f"{username} did not play in this game"
                report.rejected.append(Rejected(source, reason, game.url))
                continue

            report.valid.append(game)

    # Stop: if most games break the contract, don't trust any of them.
    if report.total and contract_failures / report.total > CONTRACT_FAILURE_LIMIT:
        raise DataContractError(
            f"{contract_failures} of {report.total} games broke the data contract. "
            "Chess.com may have changed its format."
        )

    # Timeliness: warn if there is nothing recent.
    if report.valid:
        newest = max(game.end_time for game in report.valid)
        if now - newest > STALE_AFTER:
            report.warnings.append(
                f"Newest game is from {newest:%d %b %Y}, over {STALE_AFTER.days} days ago."
            )
    else:
        report.warnings.append("No games passed the checks.")

    return report
