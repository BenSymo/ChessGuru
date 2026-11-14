"""Overview page (the home page): top 3 things to fix, then headline numbers and charts."""

from __future__ import annotations

import streamlit as st

from chessguru.app import aggregates, charts
from chessguru.app.components import cost_text, tip_badge, tips_for
from chessguru.app.context import get_context, num, pct


def render() -> None:
    ctx = get_context()
    games, moves, theme = ctx.games, ctx.moves, ctx.theme
    s = aggregates.summary(games)

    st.title("Overview")
    st.caption(
        f"Your newest {s.games} games · {s.analysed} analysed with Stockfish · "
        f"{games['date_day'].min():%d %b %Y} to {games['date_day'].max():%d %b %Y}"
    )

    st.subheader("Fix these first")
    fixes = [t for t in tips_for(ctx) if t.kind == "fix"][:3]
    if not fixes:
        st.success("No clear weaknesses in these games. Include more games for a fuller picture.")
    for column, (rank, tip) in zip(st.columns(3), enumerate(fixes, start=1), strict=False):
        with column, st.container(border=True, height="stretch"):
            st.markdown(f"**{rank}. {tip.title}**")
            tip_badge(tip)
            st.caption(f"{cost_text(tip)} · based on {tip.based_on} games")
            st.write(tip.advice)
    if fixes and "pages" in st.session_state:
        st.page_link(
            st.session_state["pages"]["tips"],
            label="See every tip, with examples",
            icon=":material/arrow_forward:",
        )

    a, b, c, d = st.columns(4)
    a.metric("Score", pct(s.score_pct), help="Wins count 1, draws ½, losses 0.")
    b.metric("Accuracy", num(s.accuracy), help="Average move accuracy (0–100), Lichess method.")
    c.metric("Blunders per game", num(s.blunders_per_game))
    d.metric("Mistakes per game", num(s.mistakes_per_game))

    st.plotly_chart(
        charts.results_bar(s.wins, s.draws, s.losses, theme),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(f"{s.wins} wins · {s.draws} draws · {s.losses} losses")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Where your bad moves happen")
        phases = aggregates.phase_stats(moves)
        st.plotly_chart(
            charts.columns(
                [p.title() for p in phases["phase"]],
                list(phases["blunders_per_game"].fillna(0) + phases["mistakes_per_game"].fillna(0))
                if not moves.empty
                else [None, None, None],
                theme,
                y_title="Mistakes + blunders per game",
                value_format=".1f",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption("Per game that reached each phase.")
    with right:
        st.subheader("Why they went wrong")
        types = aggregates.mistake_types(moves).head(6)
        if types.empty:
            st.write("No mistakes or blunders in the analysed games. Nice.")
        else:
            st.plotly_chart(
                charts.horizontal_bars(
                    list(types["name"]),
                    list(types["share"] * 100),
                    theme,
                    value_format=".0f",
                    suffix="%",
                    hover=[
                        f"{n}: {m} moves in {g} games"
                        for n, m, g in zip(
                            types["name"], types["moves"], types["games"], strict=True
                        )
                    ],
                ),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption("% of your mistakes and blunders. A move can have more than one reason.")

    st.subheader("Rating")
    trend = aggregates.rating_trend(games)
    st.plotly_chart(
        charts.rating_trend(trend, theme), width="stretch", config={"displayModeBar": False}
    )
