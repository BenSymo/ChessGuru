"""ChessGuru dashboard. Start with `chessguru dashboard` (or `streamlit run` on this file)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from chessguru import pipeline
from chessguru.app import data
from chessguru.app.context import Context, current_theme, set_context
from chessguru.app.views import endgames, health, mistakes, openings, overview, time_management
from chessguru.config import Settings

st.set_page_config(page_title="ChessGuru", page_icon="♟", layout="wide")


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data(show_spinner=False)
def cached_games(db: str, mtime: float, filters: data.Filters) -> pd.DataFrame:
    return data.load_games(Path(db), filters)


@st.cache_data(show_spinner=False)
def cached_moves(db: str, mtime: float, username: str, keys: tuple[str, ...]) -> pd.DataFrame:
    return data.load_moves(Path(db), username, list(keys))


def run_pipeline(
    settings: Settings, username: str, games: int, fetch: bool, only: list[str] | None = None
) -> None:
    """Run the pipeline from the dashboard, showing progress as it goes."""
    with st.status("Updating…", expanded=True) as status:
        try:
            if fetch:
                st.write("Downloading games from chess.com…")
                pipeline.fetch(settings, username, max_games=games)
                report = pipeline.check(settings, username)
                pipeline.parse(settings, username, report.valid)
            st.write("Analysing with Stockfish…")
            bar = st.progress(0.0)

            def progress(done: int, total: int) -> None:
                bar.progress(done / total, f"{done} of {total} games")

            summary = pipeline.analyse(
                settings, username, max_games=games, only=only, progress=progress
            )
            st.write(f"Analysed {summary.analysed} new games.")
            st.write("Building the gold tables…")
            pipeline.build(settings, username)
        except Exception as exc:  # shown to the user, not swallowed
            status.update(label="Update failed", state="error")
            st.error(str(exc))
            st.stop()
        status.update(label="Up to date", state="complete")
    st.cache_data.clear()
    st.rerun()


def first_run(settings: Settings) -> None:
    st.title("ChessGuru")
    st.write("See where you're going wrong at chess, and what to fix first.")
    with st.form("first_run"):
        username = st.text_input("Your chess.com username", value=settings.username or "")
        games = st.number_input(
            "Games to analyse", min_value=1, max_value=1000, value=settings.max_games
        )
        submitted = st.form_submit_button("Get my games", type="primary")
    st.caption("Analysing takes roughly 2–3 seconds per game, so 30 games is about a minute.")
    if submitted and username.strip():
        run_pipeline(settings, username.strip().lower(), int(games), fetch=True)


def sidebar(settings: Settings, players: list[str]) -> tuple[data.Filters, int]:
    with st.sidebar:
        st.title("♟ ChessGuru")
        default = settings.username if settings.username in players else players[0]
        username = st.selectbox("Player", players, index=players.index(default), key="player")
        everything = cached_games(
            str(settings.db_path), _mtime(settings.db_path), data.Filters(username)
        )

        classes = [
            c for c in ("bullet", "blitz", "rapid", "daily") if c in set(everything["time_class"])
        ]
        chosen = st.pills(
            "Time control", classes, selection_mode="multi", default=classes, key="time_classes"
        )
        colour = st.segmented_control(
            "Colour", ["Both", "White", "Black"], default="Both", key="colour"
        )
        rated = st.toggle("Rated games only", value=False, key="rated")
        total = len(everything)
        last_n = st.number_input(
            "Games to include (newest first)",
            min_value=1,
            max_value=max(1, total),
            value=min(settings.max_games, max(1, total)),
            step=10,
            key="last_n",
            help="Change this to look at more or fewer games. New games need analysing once.",
        )
    filters = data.Filters(
        username=username,
        time_classes=tuple(chosen or classes),
        last_n=int(last_n),
        colour=None if colour in (None, "Both") else str(colour).lower(),
        rated_only=rated,
    )
    return filters, total


def update_controls(settings: Settings, ctx: Context) -> None:
    with st.sidebar:
        st.divider()
        missing = ctx.games[~ctx.games["is_analysed"]]
        shown = len(ctx.games)
        st.caption(f"{shown - len(missing)} of {shown} games shown are analysed.")
        if len(missing) and st.button(
            f"Analyse these games ({len(missing)} to do)", type="primary"
        ):
            run_pipeline(
                settings,
                ctx.filters.username,
                len(missing),
                fetch=False,
                only=list(missing["game_uuid"]),
            )
        if st.button("Get new games from chess.com"):
            run_pipeline(
                settings, ctx.filters.username, ctx.filters.last_n or settings.max_games, fetch=True
            )


def main() -> None:
    settings = Settings()
    players = data.usernames(settings.db_path)
    if not players:
        first_run(settings)
        return

    filters, _ = sidebar(settings, players)
    db, mtime = str(settings.db_path), _mtime(settings.db_path)
    try:
        games = cached_games(db, mtime, filters)
        moves = cached_moves(
            db, mtime, filters.username, tuple(games.loc[games["is_analysed"], "game_key"])
        )
    except data.DataUnavailable as exc:
        st.warning(str(exc))
        return
    ctx = Context(
        settings=settings, filters=filters, games=games, moves=moves, theme=current_theme()
    )
    set_context(ctx)
    update_controls(settings, ctx)

    page = st.navigation(
        [
            st.Page(
                overview.render,
                title="Overview",
                icon=":material/dashboard:",
                url_path="overview",
                default=True,
            ),
            st.Page(
                openings.render, title="Openings", icon=":material/menu_book:", url_path="openings"
            ),
            st.Page(
                mistakes.render, title="Mistakes", icon=":material/error:", url_path="mistakes"
            ),
            st.Page(time_management.render, title="Time", icon=":material/timer:", url_path="time"),
            st.Page(endgames.render, title="Endgames", icon=":material/flag:", url_path="endgames"),
            st.Page(
                health.render,
                title="Data health",
                icon=":material/monitor_heart:",
                url_path="health",
            ),
        ]
    )
    if games.empty:
        st.info("No games match these filters.")
        return
    page.run()


main()
