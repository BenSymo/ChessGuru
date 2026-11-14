from __future__ import annotations

import pandas as pd
import streamlit as st

from chessguru.app import aggregates, charts, data
from chessguru.app.board import position_svg
from chessguru.app.components import VIEWER_GAME, VIEWER_PLY
from chessguru.app.context import get_context

LABEL_TEXT = {
    "best": "Best move",
    "good": "Good",
    "inaccuracy": "Inaccuracy ?!",
    "mistake": "Mistake ?",
    "blunder": "Blunder ??",
}


def _game_label(game: pd.Series) -> str:
    result = aggregates.OUTCOME_NAMES[game["outcome"]]
    return (
        f"{game['date_day']:%d %b} · {game['time_control']} · {game['player_colour'].title()} · "
        f"{game['opening_family']} · {result}"
    )


def _move_label(move: pd.Series) -> str:
    dots = "." if move["colour"] == "white" else "…"
    return f"{move['move_number']}{dots} {move['san']}"


def render() -> None:
    ctx = get_context()
    st.title("Game viewer")
    games = ctx.games
    keys = list(games["game_key"])
    wanted = st.session_state.get(VIEWER_GAME)
    index = keys.index(wanted) if wanted in keys else 0
    key = st.selectbox(
        "Game",
        keys,
        index=index,
        format_func=lambda k: _game_label(games.set_index("game_key").loc[k]),
    )
    game = games.set_index("game_key").loc[key]
    if key != wanted:
        st.session_state[VIEWER_GAME] = key
        st.session_state[VIEWER_PLY] = None

    moves = data.load_game_moves(ctx.settings.db_path, ctx.filters.username, key)
    if moves.empty:
        st.warning("No moves stored for this game.")
        return
    analysed = bool(moves["is_analysed"].all())
    player_white = game["player_colour"] == "white"

    plies = list(moves["ply"])
    start = st.session_state.get(VIEWER_PLY)
    if start not in plies:
        bad = moves[moves["is_player_move"] & moves["is_bad_move"].fillna(False)]
        start = int(bad.iloc[0]["ply"]) if len(bad) else plies[0]
    ply = st.select_slider(
        "Move",
        options=plies,
        value=start,
        format_func=lambda p: _move_label(moves.set_index("ply").loc[p]),
    )
    move = moves.set_index("ply").loc[ply]

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.image(
            position_svg(
                move["fen_before"],
                played=move["uci"],
                best=move["best_move_uci"] if analysed else None,
                bad=bool(move["is_bad_move"]) if analysed else False,
                flipped=not player_white,
                size=420,
            ),
            width=420,
        )
    with right:
        who = "You" if move["is_player_move"] else "Your opponent"
        st.subheader(f"{who}: {_move_label(move)}")
        if analysed:
            st.markdown(f"**{LABEL_TEXT.get(move['label'], move['label'])}**")
            mover_before, mover_after = move["win_before"], move["win_after"]
            st.write(f"Win chance for the side moving: {mover_before:.0f}% → {mover_after:.0f}%")
            if move["best_move_san"] and move["best_move_san"] != move["san"]:
                st.write(f"Stockfish preferred **{move['best_move_san']}** (green arrow).")
            reasons = [aggregates.TAG_NAMES.get(t, t) for t in move["tags"]]
            if reasons:
                st.write("Why: " + ", ".join(reasons))
        else:
            st.info("This game isn't analysed yet, so there's no engine verdict.")
        if pd.notna(move["clock_seconds"]):
            minutes, seconds = divmod(int(move["clock_seconds"]), 60)
            st.caption(f"Clock after the move: {minutes}:{seconds:02d}")
        st.link_button("Open on chess.com", game["url"])

    if analysed:
        white_win = [
            w if c == "white" else 100 - w
            for w, c in zip(moves["win_after"], moves["colour"], strict=True)
        ]
        bad_plies = list(moves.loc[moves["is_player_move"] & moves["is_bad_move"], "ply"])
        st.plotly_chart(
            charts.eval_chart(plies, white_win, bad_plies, ply, ctx.theme),
            width="stretch",
            config={"displayModeBar": False},
        )
        yours = moves[
            moves["is_player_move"] & moves["label"].isin(["inaccuracy", "mistake", "blunder"])
        ]
        if len(yours):
            st.subheader("Your inaccuracies, mistakes and blunders in this game")
            st.dataframe(
                yours.assign(
                    move=yours.apply(_move_label, axis=1),
                    verdict=yours["label"].map(LABEL_TEXT),
                    reasons=yours["tags"].map(
                        lambda t: ", ".join(aggregates.TAG_NAMES.get(x, x) for x in t)
                    ),
                )[["move", "verdict", "best_move_san", "win_drop", "phase", "reasons"]],
                hide_index=True,
                width="stretch",
                column_config={
                    "move": "Move",
                    "verdict": "Verdict",
                    "best_move_san": "Better was",
                    "win_drop": st.column_config.NumberColumn("Win chance lost", format="%.0f pts"),
                    "phase": "Phase",
                    "reasons": "Why",
                },
            )
