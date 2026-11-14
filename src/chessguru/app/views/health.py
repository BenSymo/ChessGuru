"""Data health page: pipeline run log, games set aside (quarantine) and row counts."""

from __future__ import annotations

import streamlit as st

from chessguru.app import data
from chessguru.app.context import get_context


def render() -> None:
    ctx = get_context()
    st.title("Data health")
    st.caption("What the pipeline has done, and any games it set aside.")
    try:
        info = data.health(ctx.settings.db_path)
    except data.DataUnavailable as exc:
        st.warning(str(exc))
        return

    counts = info["counts"]
    for column, row in zip(st.columns(len(counts)), counts.itertuples(), strict=True):
        column.metric(row.layer, f"{row.rows:,}")

    runs = info["runs"]
    failed = runs[runs["status"] != "succeeded"]
    if len(failed):
        st.error(f"{len(failed)} of the last {len(runs)} pipeline steps failed. See below.")
    else:
        st.success(f"The last {len(runs)} pipeline steps all succeeded.")

    st.subheader("Games set aside")
    if info["quarantine"].empty:
        st.write("None. Every downloaded game passed the checks.")
    else:
        st.dataframe(
            info["quarantine"],
            hide_index=True,
            width="stretch",
            column_config={
                "username": "Player",
                "step": "Step",
                "reason": "Reason",
                "games": "Games",
            },
        )

    st.subheader("Recent pipeline runs")
    st.dataframe(
        runs,
        hide_index=True,
        width="stretch",
        column_config={
            "step": "Step",
            "username": "Player",
            "status": "Status",
            "started_at": st.column_config.DatetimeColumn("Started", format="D MMM, HH:mm:ss"),
            "seconds": st.column_config.NumberColumn("Seconds", format="%.1f"),
            "details": "Details",
        },
    )
