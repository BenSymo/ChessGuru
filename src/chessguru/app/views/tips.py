from __future__ import annotations

import streamlit as st

from chessguru.app.components import tip_card, tips_for
from chessguru.app.context import get_context


def render() -> None:
    ctx = get_context()
    st.title("Tips")
    st.caption(
        f"Ranked by how much each problem cost you in your newest {len(ctx.games)} games. "
        "Fix the first one first."
    )
    with st.expander("How the cost is worked out"):
        st.markdown(
            "For bad moves, the cost is how much they lowered your chance of winning, added up "
            "for each game and capped at one game each. 1.0 means about one game's worth of "
            "points. For results (openings, colour, tilt) it is points below what you'd "
            "otherwise expect.\n\n"
            "**Clear pattern** means it showed up in 3+ games out of 15+. **Early sign** means "
            "there isn't much data yet: include more games to check it."
        )

    tips = tips_for(ctx)
    fixes = [t for t in tips if t.kind == "fix"]
    strengths = [t for t in tips if t.kind == "strength"]
    if ctx.analysed_games.empty:
        st.info("Most tips need Stockfish's analysis. Use **Analyse these games** in the sidebar.")
    if not fixes:
        st.success("No clear weaknesses in these games. Include more games for a fuller picture.")
    for rank, tip in enumerate(fixes, start=1):
        tip_card(tip, rank, key=f"tip_{tip.id}")

    if strengths:
        st.header("What you do well")
        for tip in strengths:
            tip_card(tip, None, key=f"strength_{tip.id}", examples=False)
