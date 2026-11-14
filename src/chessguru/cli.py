"""Command-line entry point: `chessguru <command>`."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

import typer

from chessguru import __version__, pipeline
from chessguru.analysis.engine import EngineError
from chessguru.api.client import ChessComError
from chessguru.config import Settings
from chessguru.quality.checks import DataContractError
from chessguru.transform.dbt import DbtError, run_dbt

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


UsernameArg = Annotated[
    str | None, typer.Argument(help="chess.com username. Defaults to CHESSGURU_USERNAME.")
]
GamesOpt = Annotated[
    int | None, typer.Option("--games", "-n", min=1, help="How many recent games to get.")
]


def _username(settings: Settings, username: str | None) -> str:
    name = (username or settings.username or "").strip().lower()
    if not name:
        typer.echo("Give a username, e.g. `chessguru fetch myname`, or set CHESSGURU_USERNAME.")
        raise typer.Exit(code=2)
    return name


@app.command()
def fetch(username: UsernameArg = None, games: GamesOpt = None) -> None:
    """Download your recent games from chess.com, check them and split them into moves."""
    settings = Settings()
    _fetch(settings, _username(settings, username), games)


DepthOpt = Annotated[
    int | None, typer.Option("--depth", "-d", min=1, max=40, help="Stockfish search depth.")
]


@app.command()
def analyse(username: UsernameArg = None, games: GamesOpt = None, depth: DepthOpt = None) -> None:
    """Analyse your newest games with Stockfish. Games already analysed are skipped."""
    settings = _with_depth(Settings(), depth)
    _analyse(settings, _username(settings, username), games)


@app.command()
def build() -> None:
    """Build and test the gold tables with dbt."""
    _build(Settings())


@app.command()
def run(username: UsernameArg = None, games: GamesOpt = None, depth: DepthOpt = None) -> None:
    """Do everything: fetch, check, split into moves, analyse, and build the gold tables."""
    settings = _with_depth(Settings(), depth)
    name = _username(settings, username)
    _fetch(settings, name, games)
    _analyse(settings, name, games)
    _build(settings)


def _with_depth(settings: Settings, depth: int | None) -> Settings:
    return settings.model_copy(update={"engine_depth": depth}) if depth else settings


def _analyse(settings: Settings, name: str, games: int | None) -> None:
    limit = games or settings.max_games
    typer.echo(f"Analysing your newest {limit} games at depth {settings.engine_depth}...")
    with typer.progressbar(length=limit, label="Games") as bar:
        last = 0

        def progress(done: int, total: int) -> None:
            nonlocal last
            bar.length = total
            bar.update(done - last)
            last = done

        try:
            summary = pipeline.analyse(settings, name, max_games=games, progress=progress)
        except EngineError as exc:
            typer.echo(f"\nError: {exc}")
            raise typer.Exit(code=1) from exc
    typer.echo(f"Analysed {summary.analysed} games ({summary.already_done} were already done)")


@app.command()
def tips(username: UsernameArg = None, games: GamesOpt = None) -> None:
    """Show what to fix first, from your newest games (run `chessguru run` first)."""
    from chessguru.app import data
    from chessguru.insights.tips import build_tips

    settings = Settings()
    name = _username(settings, username)
    limit = games or settings.max_games
    try:
        recent = data.load_games(settings.db_path, data.Filters(name, last_n=limit))
        keys = list(recent.loc[recent["is_analysed"], "game_key"])
        moves = data.load_moves(settings.db_path, name, keys)
    except data.DataUnavailable as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc
    if recent.empty:
        typer.echo(f"No games for {name} yet. Run `chessguru run {name}` first.")
        raise typer.Exit(code=1)

    found = build_tips(recent, moves)
    fixes = [t for t in found if t.kind == "fix"]
    typer.echo(f"From your newest {len(recent)} games ({len(keys)} analysed):\n")
    if not fixes:
        typer.echo("No clear weaknesses. Include more games with --games for a fuller picture.")
    for rank, tip in enumerate(fixes, start=1):
        strength = "clear pattern" if tip.firm else "early sign"
        typer.echo(f"{rank}. {tip.title}  ({tip.cost:.1f} games' worth of points, {strength})")
        typer.echo(f"   {tip.detail}")
        typer.echo(f"   What to do: {tip.advice}\n")
    for tip in (t for t in found if t.kind == "strength"):
        typer.echo(f"+ {tip.title}. {tip.detail}")


@app.command()
def dashboard(
    port: Annotated[int, typer.Option(help="Port to serve the dashboard on.")] = 8501,
) -> None:
    """Open the dashboard in your browser."""
    import subprocess
    import sys
    from pathlib import Path

    app_file = Path(__file__).parent / "app" / "main.py"
    command = [
        sys.executable, "-m", "streamlit", "run", str(app_file),
        "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
        "--client.toolbarMode", "minimal",
        # Set per theme, so Streamlit still follows the viewer's light or dark mode.
        "--theme.light.primaryColor", "#2a78d6",
        "--theme.dark.primaryColor", "#3987e5",
    ]  # fmt: skip
    raise typer.Exit(subprocess.call(command))


@app.command()
def docs() -> None:
    """Generate the dbt docs site (models, tests and lineage)."""
    settings = Settings()
    try:
        run_dbt(settings, "docs generate")
    except DbtError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc
    target = settings.dbt_target_dir.resolve()
    typer.echo(f"Docs written to {target / 'index.html'}")
    typer.echo(
        "To browse them: uv run dbt docs serve --project-dir dbt --profiles-dir dbt "
        f"--target-path {target}"
    )


def _build(settings: Settings) -> None:
    try:
        result = pipeline.build(settings)
    except DbtError as exc:
        typer.echo(f"Gold build failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"Gold tables built: {result.passed} models and tests passed")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}")


def _fetch(settings: Settings, name: str, games: int | None) -> None:
    try:
        summary = pipeline.fetch(settings, name, max_games=games)
        report = pipeline.check(settings, name)
        parsed = pipeline.parse(settings, name, report.valid)
    except (ChessComError, DataContractError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    months = ", ".join(m.key for m in summary.months) or "none"
    typer.echo(f"Months: {months}")
    typer.echo(f"  downloaded {len(summary.downloaded)}, reused {len(summary.cached)} from disk")
    limit = games or settings.max_games
    ready = len(report.valid) - len(parsed.rejected)
    typer.echo(f"Games ready: {ready} (the newest {limit} will be analysed)")
    typer.echo(f"  {parsed.parsed} new, {parsed.already_stored} already stored")
    rejected = report.rejected + parsed.rejected
    if rejected:
        typer.echo(f"Games set aside: {len(rejected)}")
        reasons = Counter(r.reason for r in rejected)
        for reason, count in reasons.most_common():
            typer.echo(f"  {count} x {reason}")
    for warning in report.warnings:
        typer.echo(f"Warning: {warning}")
