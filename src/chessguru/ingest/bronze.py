"""Bronze layer: raw monthly JSON files, stored exactly as chess.com sent them.

Layout: <data_dir>/bronze/<username>/<YYYY-MM>.json

A month's file is "complete" once it was downloaded after that month ended. Complete
files never change, so they are reused. Any other file (the current month, or a past
month first downloaded while it was still going) is downloaded again.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from chessguru.api.client import ArchiveMonth


class BronzeStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, username: str, month: ArchiveMonth) -> Path:
        return self.root / username.lower() / f"{month.key}.json"

    def is_complete(self, username: str, month: ArchiveMonth) -> bool:
        """True if the stored file was downloaded after the month ended."""
        path = self.path_for(username, month)
        if not path.exists():
            return False
        written = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        return written >= month.ends_at()

    def read(self, username: str, month: ArchiveMonth) -> bytes:
        return self.path_for(username, month).read_bytes()

    def write(self, username: str, month: ArchiveMonth, raw: bytes) -> Path:
        """Write atomically, so a crash never leaves a half-written file."""
        path = self.path_for(username, month)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    def months(self, username: str) -> list[ArchiveMonth]:
        """Months stored for this player, oldest first."""
        folder = self.root / username.lower()
        if not folder.is_dir():
            return []
        months = []
        for file in folder.glob("*.json"):
            year, _, month = file.stem.partition("-")
            if year.isdigit() and month.isdigit():
                months.append(ArchiveMonth(int(year), int(month)))
        return sorted(months)
