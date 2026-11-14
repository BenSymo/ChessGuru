"""Download a player's recent games into the bronze layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from chessguru.api.client import ArchiveMonth, ChessComClient
from chessguru.ingest.bronze import BronzeStore


@dataclass
class FetchSummary:
    username: str
    downloaded: list[ArchiveMonth] = field(default_factory=list)
    cached: list[ArchiveMonth] = field(default_factory=list)
    games_found: int = 0

    @property
    def months(self) -> list[ArchiveMonth]:
        return sorted(self.downloaded + self.cached)


def count_games(raw: bytes) -> int:
    """How many games a raw month file holds (0 if it can't be read)."""
    try:
        games = json.loads(raw).get("games", [])
    except (ValueError, AttributeError):
        return 0
    return len(games) if isinstance(games, list) else 0


def fetch_recent_games(
    client: ChessComClient,
    store: BronzeStore,
    username: str,
    max_games: int,
    today: date,
) -> FetchSummary:
    """Fetch months, newest first, until we have at least `max_games` games.

    Past months already on disk are reused, so later runs only download
    the current month and anything new.
    """
    summary = FetchSummary(username=username.lower())
    for month in reversed(client.get_archives(username)):
        if store.has(username, month) and not month.is_current(today):
            raw = store.read(username, month)
            summary.cached.append(month)
        else:
            raw = client.get_month_raw(username, month)
            store.write(username, month, raw)
            summary.downloaded.append(month)

        summary.games_found += count_games(raw)
        if summary.games_found >= max_games:
            break
    return summary
