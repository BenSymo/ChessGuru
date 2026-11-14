"""Openings page: results per opening family, as White and as Black."""

from __future__ import annotations

import streamlit as st

from chessguru.app import aggregates, charts
from chessguru.app.context import get_context


def render() -> None:
    ctx = get_context()
    st.title("Openings")
    st.caption("How each opening family goes for you. Score counts wins 1, draws ½, losses 0.")

    min_games = st.slider("Only openings with at least this many games", 1, 20, 2, key="min_games")
    table = aggregates.opening_table(ctx.games, min_games=min_games)
    if table.empty:
        st.info("No opening has that many games yet. Lower the limit, or include more games.")
        return

    for colour, column in zip(("white", "black"), st.columns(2, gap="large"), strict=True):
        part = table[table["player_colour"] == colour].head(8)
        with column:
            st.subheader(f"As {colour.title()}")
            if part.empty:
                st.write("No games.")
                continue
            st.plotly_chart(
                charts.horizontal_bars(
                    list(part["opening_family"]),
                    list(part["score_pct"] * 100),
                    ctx.theme,
                    suffix="%",
                    hover=[
                        f"{o}: {g} games, {w}W {d}D {lo}L"
                        for o, g, w, d, lo in zip(
                            part["opening_family"],
                            part["games"],
                            part["wins"],
                            part["draws"],
                            part["losses"],
                            strict=True,
                        )
                    ],
                ),
                width="stretch",
                config={"displayModeBar": False},
                key=f"openings_{colour}",
            )
            st.caption("Score % per opening, most played at the top.")

    st.subheader("All openings")
    st.dataframe(
        table.assign(player_colour=table["player_colour"].str.title()).rename(
            columns={
                "player_colour": "Colour",
                "opening_family": "Opening",
                "games": "Games",
                "wins": "Wins",
                "draws": "Draws",
                "losses": "Losses",
                "score_pct": "Score",
                "accuracy": "Accuracy",
                "last_played": "Last played",
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", format="percent", min_value=0, max_value=1
            ),
            "Accuracy": st.column_config.NumberColumn(format="%.1f"),
            "Last played": st.column_config.DateColumn(format="D MMM YYYY"),
        },
    )
