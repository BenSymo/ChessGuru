"""Command-line entry point: `chessguru <command>`."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

import typer

from chessguru import __version__, pipeline
from chessguru.api.client import ChessComError
from chessguru.config import Settings
from chessguru.quality.checks import DataContractError

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


@app.command()
def fetch(
    username: Annotated[
        str | None, typer.Argument(help="chess.com username. Defaults to CHESSGURU_USERNAME.")
    ] = None,
    games: Annotated[
        int | None, typer.Option("--games", "-n", min=1, help="How many recent games to get.")
    ] = None,
) -> None:
    """Download your recent games from chess.com and check them."""
    settings = Settings()
    name = (username or settings.username or "").strip().lower()
    if not name:
        typer.echo("Give a username, e.g. `chessguru fetch myname`, or set CHESSGURU_USERNAME.")
        raise typer.Exit(code=2)

    try:
        summary = pipeline.fetch(settings, name, max_games=games)
        report = pipeline.check(settings, name)
    except (ChessComError, DataContractError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    months = ", ".join(m.key for m in summary.months) or "none"
    typer.echo(f"Months: {months}")
    typer.echo(f"  downloaded {len(summary.downloaded)}, reused {len(summary.cached)} from disk")
    limit = games or settings.max_games
    typer.echo(f"Games ready: {len(report.valid)} (the newest {limit} will be analysed)")
    if report.rejected:
        typer.echo(f"Games set aside: {len(report.rejected)}")
        reasons = Counter(r.reason for r in report.rejected)
        for reason, count in reasons.most_common():
            typer.echo(f"  {count} x {reason}")
    for warning in report.warnings:
        typer.echo(f"Warning: {warning}")
