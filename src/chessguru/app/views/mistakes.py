from __future__ import annotations

import streamlit as st

from chessguru.app import aggregates, charts
from chessguru.app.context import get_context, needs_analysis, num


def render() -> None:
    ctx = get_context()
    st.title("Mistakes")
    if needs_analysis(ctx):
        return
    moves, theme = ctx.moves, ctx.theme

    st.caption("A mistake loses 10+ points of win chance; a blunder 15+ (Lichess's thresholds).")
    phases = aggregates.phase_stats(moves)
    cols = st.columns(3)
    for column, row in zip(cols, phases.itertuples(), strict=True):
        column.metric(
            f"{row.phase.title()} accuracy",
            num(row.accuracy),
            help=f"{row.moves} of your moves in {row.games} games",
        )
        column.caption(
            f"{num(row.blunders_per_game)} blunders and {num(row.mistakes_per_game)} "
            "mistakes per game"
        )

    st.subheader("Why your bad moves went wrong")
    types = aggregates.mistake_types(moves)
    if types.empty:
        st.write("No mistakes or blunders in the analysed games.")
    else:
        st.plotly_chart(
            charts.horizontal_bars(
                list(types["name"]),
                list(types["moves"]),
                theme,
                hover=[
                    f"{n}: in {g} games" for n, g in zip(types["name"], types["games"], strict=True)
                ],
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption("Number of mistakes and blunders with each reason.")

    st.subheader("Your costliest moves")
    worst = aggregates.worst_moves(moves, ctx.games, limit=15)
    if worst.empty:
        return
    st.dataframe(
        worst.assign(
            move=worst["move_number"].astype(str)
            + (worst["player_colour"].map({"white": ". ", "black": "… "}))
            + worst["san"],
            phase=worst["phase"].str.title(),
            reasons=worst["tags"].map(
                lambda t: ", ".join(aggregates.TAG_NAMES.get(x, x) for x in t)
            ),
        )[
            [
                "date_day",
                "time_control",
                "opening_family",
                "move",
                "best_move_san",
                "win_drop",
                "phase",
                "reasons",
                "url",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "date_day": st.column_config.DateColumn("Date", format="D MMM YYYY"),
            "time_control": "Time control",
            "opening_family": "Opening",
            "move": "You played",
            "best_move_san": "Better was",
            "win_drop": st.column_config.NumberColumn("Win chance lost", format="%.0f pts"),
            "phase": "Phase",
            "reasons": "Why",
            "url": st.column_config.LinkColumn("Game", display_text="Open"),
        },
    )
