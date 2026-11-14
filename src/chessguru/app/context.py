"""What every page needs: settings, filters and the loaded data for this run."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from chessguru.app.charts import DARK, LIGHT, Theme
from chessguru.app.data import Filters
from chessguru.config import Settings


@dataclass
class Context:
    settings: Settings
    filters: Filters
    games: pd.DataFrame
    moves: pd.DataFrame
    theme: Theme

    @property
    def analysed_games(self) -> pd.DataFrame:
        return self.games[self.games["is_analysed"]]


def set_context(ctx: Context) -> None:
    st.session_state["ctx"] = ctx


def get_context() -> Context:
    ctx: Context = st.session_state["ctx"]
    return ctx


def current_theme() -> Theme:
    return DARK if st.context.theme.type == "dark" else LIGHT


def pct(value: float | None, digits: int = 0) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.{digits}%}"


def num(value: float | None, digits: int = 1) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.{digits}f}"


def needs_analysis(ctx: Context) -> bool:
    """Show a note on engine-based pages when nothing shown is analysed."""
    if ctx.analysed_games.empty:
        st.info(
            "None of the games shown have been analysed yet. "
            "Use **Analyse these games** in the sidebar."
        )
        return True
    return False
