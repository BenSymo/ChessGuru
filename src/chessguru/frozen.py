"""Support for the packaged app (ChessGuru.exe, built with PyInstaller).

When the app is packaged, Python, the libraries, the dbt project and Stockfish all
sit inside the app's own folder, and there is no project folder or .env next to it.
These helpers say where things are in that case.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

# The packaged app runs dbt by starting itself again with this first argument.
DBT_COMMAND = "__dbt__"


def is_frozen() -> bool:
    """True when running as the packaged app rather than from source."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Folder holding the packaged app's bundled files."""
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))


def app_data_dir() -> Path:
    """Per-user folder for games, the database and settings in the packaged app.

    Windows: %LOCALAPPDATA%\\ChessGuru. Elsewhere: ~/.chessguru.
    """
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "ChessGuru" if local else Path.home() / ".chessguru"


def bundled_stockfish() -> Path | None:
    """The Stockfish binary shipped inside the packaged app, if there is one."""
    if not is_frozen():
        return None
    folder = bundle_dir() / "stockfish"
    for name in ("stockfish.exe", "stockfish"):
        if (folder / name).exists():
            return folder / name
    return None


def dbt_command() -> list[str]:
    """How to start dbt in its own process."""
    if is_frozen():
        return [sys.executable, DBT_COMMAND]
    return [sys.executable, "-c", "from dbt.cli.main import cli; cli()"]


def main() -> None:
    """Entry point of the packaged app.

    - `ChessGuru.exe` with no arguments (a double-click) opens the dashboard.
    - `ChessGuru.exe __dbt__ ...` runs dbt (used internally by the gold build).
    - Anything else is the normal `chessguru` command line.
    """
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == DBT_COMMAND:
        from dbt.cli.main import cli

        sys.argv = ["dbt", *sys.argv[2:]]
        cli()
        return
    if len(sys.argv) == 1:
        sys.argv.append("dashboard")

    from chessguru.cli import app

    app()
