"""Command-line entry point: `chessguru <command>`."""

from __future__ import annotations

import typer

from chessguru import __version__
from chessguru.config import Settings

app = typer.Typer(
    help="See where you're going wrong at chess and what to fix first.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """ChessGuru command-line tool."""


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Check your settings and that Stockfish can be found."""
    settings = Settings()
    stockfish = settings.resolve_stockfish()
    rows = [
        ("Username", settings.username or "not set (pass it on the command line)"),
        ("Contact", settings.contact or "not set (chess.com asks for one)"),
        ("Data folder", str(settings.data_dir)),
        ("Stockfish", str(stockfish) if stockfish else "NOT FOUND"),
        ("Engine depth", str(settings.engine_depth)),
        ("Games to analyse", str(settings.max_games)),
        ("Hash key", "set" if settings.hash_key else "not set"),
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        typer.echo(f"{label:<{width}}  {value}")

    if stockfish is None:
        typer.echo("\nStockfish is needed for analysis. See the README for how to install it.")
        raise typer.Exit(code=1)
