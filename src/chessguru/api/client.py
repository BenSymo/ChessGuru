"""A small, polite client for the chess.com Published-Data API.

Chess.com asks API users to:
- send a User-Agent with contact details,
- make requests one at a time (parallel requests get HTTP 429).

This client does both, and retries on 429 and server errors with backoff.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Self

import httpx

BASE_URL = "https://api.chess.com/pub"
_ARCHIVE_RE = re.compile(r"/games/(\d{4})/(\d{2})$")
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class ChessComError(Exception):
    """The chess.com API could not be reached or returned an error."""


class PlayerNotFoundError(ChessComError):
    """No chess.com player has this username."""


@dataclass(frozen=True, order=True)
class ArchiveMonth:
    """One month of a player's games, e.g. 2026-11."""

    year: int
    month: int

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def is_current(self, today: date) -> bool:
        """The current month is still changing; past months never do."""
        return (self.year, self.month) == (today.year, today.month)

    @classmethod
    def from_url(cls, url: str) -> ArchiveMonth:
        match = _ARCHIVE_RE.search(url)
        if not match:
            raise ChessComError(f"Unexpected archive URL: {url}")
        return cls(int(match.group(1)), int(match.group(2)))


class ChessComClient:
    def __init__(
        self,
        user_agent: str,
        *,
        delay: float = 0.2,
        max_retries: int = 4,
        backoff: float = 1.0,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )
        self._delay = delay
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep
        self._last_request: float | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def get_archives(self, username: str) -> list[ArchiveMonth]:
        """Months that have games for this player, oldest first."""
        response = self._get(f"/player/{username.lower()}/games/archives", username)
        urls = response.json().get("archives", [])
        return sorted(ArchiveMonth.from_url(url) for url in urls)

    def get_month_raw(self, username: str, month: ArchiveMonth) -> bytes:
        """The raw JSON for one month of games, exactly as chess.com sent it."""
        path = f"/player/{username.lower()}/games/{month.year:04d}/{month.month:02d}"
        return self._get(path, username).content

    def _get(self, path: str, username: str) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            self._wait_politely()
            try:
                response = self._http.get(path)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise ChessComError(f"Could not reach chess.com: {exc}") from exc
                self._sleep(self._backoff * float(2**attempt))
                continue

            if response.status_code == 404:
                raise PlayerNotFoundError(f'No chess.com player called "{username}".')
            if response.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                self._sleep(self._retry_wait(response, attempt))
                continue
            if response.is_error:
                raise ChessComError(f"chess.com returned HTTP {response.status_code} for {path}.")
            return response
        raise AssertionError("unreachable")  # pragma: no cover

    def _wait_politely(self) -> None:
        now = time.monotonic()
        if self._last_request is not None:
            gap = now - self._last_request
            if gap < self._delay:
                self._sleep(self._delay - gap)
        self._last_request = time.monotonic()

    def _retry_wait(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return float(retry_after)
        return self._backoff * float(2**attempt)
