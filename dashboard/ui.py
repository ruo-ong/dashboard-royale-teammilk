"""Report look and feel: light grey page, dark title bar, dark headline tiles with coloured icons, white chart cards.

Every page is built from the same pieces:
    header("Title", "one-line description")
    summary("Plain-language summary in full sentences ...")
    kpis([tile("Label", "$1.2M", "note", "payments", "green"), ...])
    with card("Chart title", "what the chart shows"):
        plot(fig)
    with detail():            # technical tables and evidence for advanced readers
        ...
"""
from __future__ import annotations

import html
import re

import plotly.graph_objects as go
import streamlit as st

BLUE = "#1f6fe5"      # primary series (validated with the light-blue pair for colour-blind safety)
LIGHT_BLUE = "#3fc3ef"
ICON_COLORS = {"blue": ("#3a9bff", "#0b5fe0"), "yellow": ("#ffd23f", "#f5a300"), "purple": ("#9a8cff", "#5b48e8"),
               "teal": ("#37e6c9", "#0fb59a"), "green": ("#6be36b", "#1fae3a"), "orange": ("#ffa36a", "#ec6a2c"),
               "red": ("#ff7b7b", "#d03b3b"), "grey": ("#b9b9b9", "#7d7d7d")}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,1,0');
html, body, .stApp, .stMarkdown, .stCaption, button, input, label, textarea {
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }
.stApp, [data-testid="stAppViewContainer"] { background: #eceef1; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1440px; }
.pbi-header { background: #2e2e2e; color: #fff; border-radius: 6px; padding: 14px 22px; display: flex;
  justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; }
.pbi-header .t { font-size: 19px; font-weight: 600; letter-spacing: .1px; }
.pbi-header .s { font-size: 12.5px; color: #d6d6d6; margin-top: 2px; }
.pbi-header .chip { font-size: 12px; color: #fff; border-bottom: 2px solid #fff; padding-bottom: 4px; white-space: nowrap; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 2px 0 14px; }
.kpi { background: #111214; border-radius: 8px; padding: 14px 16px; display: flex; justify-content: space-between;
  align-items: center; min-height: 92px; box-shadow: 0 1px 3px rgba(0,0,0,.18); }
.kpi .l { font-size: 11.5px; color: #c9c9c9; }
.kpi .v { font-size: 23px; font-weight: 600; color: #fff; line-height: 1.25; margin-top: 2px; }
.kpi .n { font-size: 11px; color: #a3a3a3; margin-top: 3px; }
.kpi .i { width: 44px; height: 44px; border-radius: 11px; display: flex; align-items: center; justify-content: center;
  flex: 0 0 44px; margin-left: 10px; }
.kpi .i span { font-family: 'Material Symbols Rounded'; font-size: 26px; color: #fff; font-variation-settings: 'FILL' 1; }
div[class*="st-key-card_"] { background: #fff; border: 1px solid #e2e4e8; border-radius: 8px; padding: 14px 16px 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,.05); }
.card-t { font-size: 14px; font-weight: 600; color: #1d1d1d; }
.card-s { font-size: 12px; color: #7b7b7b; margin: 1px 0 4px; }
div[class*="st-key-summary_"] { background: #fff; border: 1px solid #e2e4e8; border-left: 4px solid #1f6fe5;
  border-radius: 6px; padding: 14px 20px 4px; }
div[class*="st-key-summary_"] p, div[class*="st-key-summary_"] li { font-size: 15px; line-height: 1.65; color: #232323; }
.sec { font-size: 15px; font-weight: 600; color: #2e2e2e; margin: 18px 0 8px; }
[data-testid="stExpander"] { background: #fff; border-radius: 6px; }
[data-testid="stSidebar"] { background: #f7f7f8; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "x"


def header(title: str, subtitle: str | None = None, chip: str | None = None) -> None:
    from common import date_range
    if chip is None:
        s, e = date_range()
        chip = f"Period: {s:%b %-d} – {e:%b %-d, %Y}"
    sub = f'<div class="s">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="pbi-header"><div><div class="t">{html.escape(title)}</div>{sub}</div>'
                f'<div class="chip">{html.escape(chip)}</div></div>', unsafe_allow_html=True)


def tile(label: str, value: str, note: str = "", icon: str = "insights", color: str = "blue") -> dict:
    return {"label": label, "value": value, "note": note, "icon": icon, "color": color}


def kpis(tiles: list[dict]) -> None:
    parts = []
    for t in tiles:
        a, b = ICON_COLORS.get(t["color"], ICON_COLORS["blue"])
        note = f'<div class="n">{html.escape(t["note"])}</div>' if t["note"] else ""
        parts.append(f'<div class="kpi"><div><div class="l">{html.escape(t["label"])}</div><div class="v">{html.escape(t["value"])}</div>'
                     f'{note}</div><div class="i" style="background:linear-gradient(135deg,{a},{b})"><span>{t["icon"]}</span></div></div>')
    st.markdown(f'<div class="kpi-row">{"".join(parts)}</div>', unsafe_allow_html=True)


def card(title: str, subtitle: str | None = None, key: str | None = None):
    box = st.container(key=f"card_{key or _slug(title)}")
    sub = f'<div class="card-s">{html.escape(subtitle)}</div>' if subtitle else ""
    box.markdown(f'<div class="card-t">{html.escape(title)}</div>{sub}', unsafe_allow_html=True)
    return box


def summary(text: str, key: str = "main") -> None:
    """The plain-language summary at the top of a page (markdown allowed)."""
    with st.container(key=f"summary_{key}"):
        st.markdown(text)


def section(title: str) -> None:
    st.markdown(f'<div class="sec">{html.escape(title)}</div>', unsafe_allow_html=True)


def detail(label: str = "Technical detail (for analysts)"):
    return st.expander(label)


def plot(fig: go.Figure, height: int | None = None, key: str | None = None, legend_top: bool = False) -> None:
    """Card-style chart: the card shows the title, so the chart's own title is removed."""
    fig.update_layout(title={"text": "", "subtitle": {"text": ""}}, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      font={"size": 11.5, "color": "#3b3b3b"}, margin={"t": 34 if legend_top else 12, "b": 40, "l": 8, "r": 12})
    if legend_top:
        fig.update_layout(legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "xanchor": "left"})
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(gridcolor="#eef0f2", linecolor="#d9dce1", automargin=True)
    fig.update_yaxes(gridcolor="#eef0f2", linecolor="#d9dce1", automargin=True)
    st.plotly_chart(fig, width="stretch", key=key, theme=None, config={"displaylogo": False, "displayModeBar": False})
