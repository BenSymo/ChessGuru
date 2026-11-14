from __future__ import annotations

import streamlit as st

from chessguru.app import aggregates, charts
from chessguru.app.context import get_context, needs_analysis, num, pct


def render() -> None:
    ctx = get_context()
    st.title("Endgames and winning positions")
    if needs_analysis(ctx):
        return
    games, moves = ctx.analysed_games, ctx.moves

    conv = aggregates.conversion(games)
    phases = aggregates.phase_stats(moves).set_index("phase")
    a, b, c = st.columns(3)
    a.metric(
        "Winning positions converted",
        pct(conv.rate),
        help="Games where you reached a 75%+ chance to win (about +3), and how many you won.",
    )
    a.caption(f"{conv.won} won, {conv.drawn} drawn, {conv.lost} lost of {conv.winning_games}")
    b.metric("Endgame accuracy", num(phases.loc["endgame", "accuracy"]))
    b.caption(f"Middlegame: {num(phases.loc['middlegame', 'accuracy'])}")
    c.metric("Games that reached an endgame", aggregates.endgame_games(moves))

    st.subheader("How your games finish")
    endings = aggregates.endings(ctx.games)
    headings = {"win": "Wins", "draw": "Draws", "loss": "Losses"}
    for outcome, column in zip(headings, st.columns(3, gap="large"), strict=True):
        part = endings[endings["outcome"] == outcome]
        with column:
            st.markdown(f"**{headings[outcome]}**")
            if part.empty:
                st.write("None.")
                continue
            st.plotly_chart(
                charts.horizontal_bars(
                    list(part["name"]),
                    list(part["games"]),
                    ctx.theme,
                    colour=charts.RESULT_COLOURS[outcome],
                ),
                width="stretch",
                config={"displayModeBar": False},
                key=f"endings_{outcome}",
            )

    slipped = games[games["failed_to_convert"]]
    if len(slipped):
        st.subheader("Winning positions you didn't win")
        slipped = slipped.assign(
            outcome=slipped["outcome"].map(aggregates.OUTCOME_NAMES),
            end_reason=slipped["end_reason"].map(lambda r: aggregates.END_REASONS.get(r, r)),
        )
        st.dataframe(
            slipped[
                [
                    "date_day",
                    "time_control",
                    "opening_family",
                    "outcome",
                    "end_reason",
                    "peak_win_chance",
                    "url",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "date_day": st.column_config.DateColumn("Date", format="D MMM YYYY"),
                "time_control": "Time control",
                "opening_family": "Opening",
                "outcome": "Result",
                "end_reason": "How it ended",
                "peak_win_chance": st.column_config.NumberColumn(
                    "Best win chance", format="%.0f%%"
                ),
                "url": st.column_config.LinkColumn("Game", display_text="Open"),
            },
        )
