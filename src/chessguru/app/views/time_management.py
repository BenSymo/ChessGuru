from __future__ import annotations

import streamlit as st

from chessguru.app import aggregates, charts
from chessguru.app.context import get_context, pct


def render() -> None:
    ctx = get_context()
    st.title("Time")
    games, moves, theme = ctx.games, ctx.moves, ctx.theme

    losses = aggregates.time_losses(games)
    a, b, c = st.columns(3)
    a.metric("Losses", losses["losses"])
    b.metric("Lost on time", losses["lost_on_time"])
    c.metric(
        "Lost on time while winning",
        losses["lost_on_time_while_winning"],
        help="You had a 75%+ chance to win (about +3) at some point, then flagged.",
    )

    if moves.empty:
        st.info("Analyse the games shown to see how your clock affects your play.")
        return

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Time per move")
        profile = aggregates.time_by_move(moves, games)
        if profile.empty:
            st.write("No clock data in these games.")
        else:
            st.plotly_chart(
                charts.time_per_move(profile, theme),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption("Average seconds you spent on each move number.")
    with right:
        st.subheader("Bad moves by clock left")
        risk = aggregates.bad_moves_by_clock(moves)
        st.plotly_chart(
            charts.columns(
                list(risk["clock_left"]),
                [None if r is None else r * 100 for r in risk["bad_rate"]],
                theme,
                y_title="% of moves that were mistakes or blunders",
                value_format=".1f",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        worst = risk.dropna(subset=["bad_rate"])
        if len(worst):
            low = worst.iloc[0]
            st.caption(
                f"With under 10% of your clock left, {pct(low['bad_rate'], 1)} of moves "
                f"were mistakes or blunders ({low['moves']} moves)."
                if low["clock_left"] == "Under 10%"
                else "You rarely get below 10% of your clock."
            )
