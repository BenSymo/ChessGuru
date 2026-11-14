"""Plotly charts in one consistent style, for light and dark themes.

Colours come from a palette checked for colour-blind safety. Each time class
always gets the same colour; results use the status colours, always with a label.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go


@dataclass(frozen=True)
class Theme:
    series: tuple[str, ...]
    text: str
    text_muted: str
    grid: str
    baseline: str
    surface: str


LIGHT = Theme(
    series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100"),
    text="#0b0b0b",
    text_muted="#52514e",
    grid="#e1e0d9",
    baseline="#c3c2b7",
    surface="#fcfcfb",
)
DARK = Theme(
    series=("#3987e5", "#d95926", "#199e70", "#c98500"),
    text="#f0efec",
    text_muted="#c3c2b7",
    grid="#2c2c2a",
    baseline="#383835",
    surface="#1a1a19",
)

GOOD, NEUTRAL, CRITICAL, WARNING = "#0ca30c", "#898781", "#d03b3b", "#fab219"
RESULT_COLOURS = {"win": GOOD, "draw": NEUTRAL, "loss": CRITICAL}
TIME_CLASSES = ("bullet", "blitz", "rapid", "daily")
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def time_class_colour(theme: Theme, time_class: str) -> str:
    index = TIME_CLASSES.index(time_class) if time_class in TIME_CLASSES else 0
    return theme.series[index]


def _style(fig: go.Figure, theme: Theme, height: int = 320, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": theme.text_muted, "size": 13},
        showlegend=legend,
        legend={"orientation": "h", "y": 1.08, "x": 0, "font": {"color": theme.text}},
        hoverlabel={"bgcolor": theme.surface, "font": {"color": theme.text, "family": FONT}},
        bargap=0.35,
    )
    axis = {
        "gridcolor": theme.grid,
        "linecolor": theme.baseline,
        "zerolinecolor": theme.baseline,
        "tickfont": {"color": theme.text_muted},
        "title": {"font": {"color": theme.text_muted}},
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def rating_trend(trend: pd.DataFrame, theme: Theme) -> go.Figure:
    fig = go.Figure()
    for time_class, part in trend.groupby("time_class"):
        colour = time_class_colour(theme, str(time_class))
        name = str(time_class).title()
        fig.add_scatter(
            x=part["end_time"],
            y=part["rating"],
            name=name,
            mode="lines",
            line={"color": colour, "width": 2},
            hovertemplate="%{x|%d %b %Y, %H:%M}<br>Rating %{y}<extra>%{fullData.name}</extra>",
        )
        # Mark and label only the latest rating.
        fig.add_scatter(
            x=part["end_time"].tail(1),
            y=part["rating"].tail(1),
            mode="markers+text",
            marker={"size": 8, "color": colour, "line": {"color": theme.surface, "width": 2}},
            text=[f"{int(part['rating'].iloc[-1])}"],
            textposition="middle right",
            textfont={"color": theme.text},
            showlegend=False,
            hoverinfo="skip",
            cliponaxis=False,
        )
    fig = _style(fig, theme, legend=trend["time_class"].nunique() > 1)
    fig.update_yaxes(title_text="Rating", tickformat="d")
    fig.update_xaxes(showgrid=False)
    fig.update_layout(margin={"l": 8, "r": 56, "t": 8, "b": 8})
    return fig


def results_bar(wins: int, draws: int, losses: int, theme: Theme) -> go.Figure:
    """One horizontal bar split into wins, draws and losses."""
    total = max(1, wins + draws + losses)
    fig = go.Figure()
    for name, value, colour in (
        ("Wins", wins, GOOD),
        ("Draws", draws, NEUTRAL),
        ("Losses", losses, CRITICAL),
    ):
        share = value / total
        fig.add_bar(
            y=[""],
            x=[value],
            name=name,
            orientation="h",
            marker={"color": colour, "line": {"color": theme.surface, "width": 2}},
            text=[f"{name} {value}" if share > 0.12 else ""],
            textposition="inside",
            insidetextanchor="start",
            textfont={"color": "#ffffff"},
            hovertemplate=f"{name}: %{{x}} ({share:.0%})<extra></extra>",
        )
    fig = _style(fig, theme, height=64, legend=False)
    fig.update_layout(barmode="stack", bargap=0)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def horizontal_bars(
    labels: list[str],
    values: list[float],
    theme: Theme,
    value_format: str = ".0f",
    hover: list[str] | None = None,
    colour: str | None = None,
    height: int | None = None,
    suffix: str = "",
) -> go.Figure:
    """Ranked horizontal bars, biggest at the top, value at the tip."""
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker={"color": colour or theme.series[0], "cornerradius": 4},
            text=[f"{v:{value_format}}{suffix}" for v in values],
            textposition="outside",
            textfont={"color": theme.text},
            cliponaxis=False,
            customdata=hover or labels,
            hovertemplate="%{customdata}<extra></extra>",
            width=0.6,
        )
    )
    # About 40px per bar keeps each bar near 24px thick, however many there are.
    fig = _style(fig, theme, height=height or 40 * len(labels) + 24)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont={"color": theme.text})
    fig.update_xaxes(showgrid=True, zeroline=False, showticklabels=False)
    fig.update_layout(margin={"l": 8, "r": 48, "t": 8, "b": 8})
    return fig


def columns(
    labels: list[str],
    values: list[float | None],
    theme: Theme,
    y_title: str,
    value_format: str = ".0f",
    colour: str | None = None,
) -> go.Figure:
    shown = [v if v is not None else 0 for v in values]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=shown,
            marker={"color": colour or theme.series[0], "cornerradius": 4},
            text=[f"{v:{value_format}}" if v is not None else "–" for v in values],
            textposition="outside",
            textfont={"color": theme.text},
            cliponaxis=False,
            hovertemplate="%{x}: %{text}<extra></extra>",
            width=0.3,
        )
    )
    fig = _style(fig, theme)
    fig.update_yaxes(title_text=y_title, rangemode="tozero")
    fig.update_xaxes(showgrid=False, tickfont={"color": theme.text})
    return fig


def time_per_move(profile: pd.DataFrame, theme: Theme) -> go.Figure:
    fig = go.Figure()
    for time_class, part in profile.groupby("time_class"):
        colour = time_class_colour(theme, str(time_class))
        fig.add_scatter(
            x=part["move_number"],
            y=part["seconds"],
            name=str(time_class).title(),
            mode="lines",
            line={"color": colour, "width": 2},
            customdata=part["moves"],
            hovertemplate="Move %{x}: %{y:.1f}s on average (%{customdata} moves)"
            "<extra>%{fullData.name}</extra>",
        )
    fig = _style(fig, theme, legend=profile["time_class"].nunique() > 1)
    fig.update_xaxes(title_text="Move number")
    fig.update_yaxes(title_text="Seconds per move", rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    return fig


def eval_chart(
    plies: list[int],
    white_win: list[float],
    bad_plies: list[int],
    selected: int | None,
    theme: Theme,
) -> go.Figure:
    """White's chance of winning after each move. Your mistakes are marked."""
    fig = go.Figure()
    fig.add_scatter(
        x=plies,
        y=white_win,
        mode="lines",
        line={"color": theme.series[0], "width": 2},
        fill="tozeroy",
        fillcolor="rgba(42,120,214,0.10)",
        hovertemplate="Ply %{x}: White %{y:.0f}%<extra></extra>",
        showlegend=False,
    )
    marks = [(p, w) for p, w in zip(plies, white_win, strict=True) if p in set(bad_plies)]
    if marks:
        fig.add_scatter(
            x=[p for p, _ in marks],
            y=[w for _, w in marks],
            mode="markers",
            name="Your mistakes and blunders",
            marker={"size": 10, "color": CRITICAL, "line": {"color": theme.surface, "width": 2}},
            hovertemplate="Your mistake at ply %{x}<extra></extra>",
        )
    if selected is not None:
        fig.add_vline(x=selected, line={"color": theme.text_muted, "width": 1})
    fig.add_hline(y=50, line={"color": theme.baseline, "width": 1})
    fig = _style(fig, theme, height=240, legend=bool(marks))
    fig.update_yaxes(range=[0, 100], title_text="White's win chance (%)")
    fig.update_xaxes(title_text="Ply (half-move)", showgrid=False)
    return fig
