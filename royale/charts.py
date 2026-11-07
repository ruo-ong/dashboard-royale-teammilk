"""One chart style for the whole team (Plotly). Same functions work in scripts and in the Streamlit app.

    from royale.charts import COLORS, style, save
    fig = go.Figure(...)
    style(fig, "Takeaway as the title", "What is plotted, units, period")
    save(fig, "a3_luck_z_hist")      # outputs/charts/a3_luck_z_hist.html (+ .png when Chrome is available)

Rules (dataviz skill): the title states the takeaway; one y-axis; thin marks; recessive grid;
categorical colors in fixed order (series_1, series_2, ...); sequential = one hue light->dark.
"""
from __future__ import annotations

import plotly.graph_objects as go

from royale.paths import OUTPUTS

COLORS = {
    "surface": "#fcfcfb",
    "text": "#0b0b0b",
    "text_secondary": "#52514e",
    "grid": "#e4e3df",
    "neutral": "#b5b3ad",      # context marks (everything that is not the focus)
    "series_1": "#2a78d6",     # blue
    "series_2": "#eb6834",     # orange: highlight (e.g. the manager's 10)
    "series_3": "#1baf7a",     # aqua
    "critical": "#d03b3b",     # status only, always with a label
}
# Sequential blue, light -> dark (magnitude: TPAH on the floor map, heatmaps).
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FONT = "Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"


def style(fig: go.Figure, title: str, subtitle: str | None = None, height: int = 480) -> go.Figure:
    text = f"<b>{title}</b>" + (f"<br><span style='font-size:13px;color:{COLORS['text_secondary']}'>{subtitle}</span>" if subtitle else "")
    fig.update_layout(
        title={"text": text, "x": 0, "xanchor": "left", "y": 0.97, "yanchor": "top", "font": {"size": 18},
               "pad": {"l": 16}},
        font={"family": FONT, "size": 13, "color": COLORS["text"]},
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        height=height,
        margin={"l": 64, "r": 24, "t": 96 if subtitle else 72, "b": 56},
        hoverlabel={"bgcolor": "white", "bordercolor": COLORS["grid"], "font": {"family": FONT, "color": COLORS["text"]}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1, "bgcolor": "rgba(0,0,0,0)"},
    )
    axis = {"gridcolor": COLORS["grid"], "linecolor": COLORS["grid"], "zerolinecolor": COLORS["grid"],
            "tickfont": {"color": COLORS["text_secondary"]}, "title": {"font": {"color": COLORS["text_secondary"]}}}
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def save(fig: go.Figure, name: str, png: bool = True) -> None:
    """Write outputs/charts/<name>.html, and a .png if Kaleido + Chrome are available (silently skipped otherwise)."""
    folder = OUTPUTS / "charts"
    folder.mkdir(parents=True, exist_ok=True)
    fig.write_html(folder / f"{name}.html", include_plotlyjs="cdn")
    if png:
        try:
            fig.write_image(folder / f"{name}.png", width=1100, height=fig.layout.height or 480, scale=2)
        except Exception as error:  # no Chrome / no kaleido: HTML is enough
            print(f"  (PNG skipped for {name}: {type(error).__name__})")
