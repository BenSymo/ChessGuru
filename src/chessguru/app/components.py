"""Pieces shared by several pages."""

from __future__ import annotations

import chess
import streamlit as st

from chessguru.app.board import position_svg, san_to_uci
from chessguru.app.context import Context
from chessguru.insights.tips import Example, Tip

VIEWER_GAME = "viewer_game"
VIEWER_PLY = "viewer_ply"


def open_in_viewer(game_key: str, ply: int | None) -> None:
    st.session_state[VIEWER_GAME] = game_key
    st.session_state[VIEWER_PLY] = ply
    st.switch_page(st.session_state["pages"]["viewer"])


def cost_text(tip: Tip) -> str:
    games = "game" if round(tip.cost, 1) == 1 else "games"
    return f"≈ {tip.cost:.1f} {games}' worth of points"


def tip_badge(tip: Tip) -> None:
    if tip.kind == "strength":
        st.badge("Strength", icon=":material/thumb_up:", color="green")
    elif tip.firm:
        st.badge("Clear pattern", icon=":material/check_circle:", color="blue")
    else:
        st.badge("Early sign", icon=":material/schedule:", color="orange")


def tip_card(tip: Tip, rank: int | None, key: str, examples: bool = True) -> None:
    with st.container(border=True):
        title = f"{rank}. {tip.title}" if rank else tip.title
        st.markdown(f"#### {title}")
        tip_badge(tip)
        facts = [tip.area]
        if tip.kind == "fix":
            facts.append(cost_text(tip))
        facts.append(f"based on {tip.based_on} games")
        st.caption(" · ".join(facts))
        st.write(tip.detail)
        st.markdown(f"**What to do:** {tip.advice}")
        if examples and tip.examples:
            example_row(tip.examples, key)


def example_row(examples: list[Example], key: str) -> None:
    columns = st.columns(3)
    for i, (example, column) in enumerate(zip(examples, columns, strict=False)):
        with column:
            if example.fen:
                board = chess.Board(example.fen)
                played = san_to_uci(example.fen, example.played)
                best = san_to_uci(example.fen, example.best)
                st.image(
                    position_svg(
                        example.fen,
                        played,
                        best,
                        bad=True,
                        flipped=board.turn == chess.BLACK,
                        size=240,
                    ),
                    width=240,
                )
                move_no = f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '…'}"
                line = f"You played **{move_no} {example.played}**"
                if example.best and example.best != example.played:
                    line += f", better was **{example.best}**"
                st.markdown(line)
                if example.win_drop:
                    st.caption(f"Lost {example.win_drop:.0f} points of win chance")
            if example.note:
                st.caption(example.note)
            date = f"{example.date_day:%d %b %Y}" if example.date_day else ""
            if st.button(
                "Open in Game Viewer", key=f"{key}_{i}", icon=":material/chess:", help=date
            ):
                open_in_viewer(example.game_key, example.ply)
            st.link_button("Open on chess.com", example.url, type="tertiary")


def tips_for(ctx: Context) -> list[Tip]:
    from chessguru.insights.tips import build_tips

    return build_tips(ctx.games, ctx.moves)
