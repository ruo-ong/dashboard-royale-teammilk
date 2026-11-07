"""Report look and feel, after the Horizon admin dashboard: lavender page, white rounded cards with soft shadows,
large bold navy titles, round icon badges, indigo + cyan charts.

Every page is built from the same pieces:
    header("Page title", "one-line description")
    key_points(["short point", ...], more="longer explanation (collapsed)")
    kpis([tile("Label", "$1,234", "note", "payments", "indigo"), ...])
    section("Section title")
    with card("Chart title", "what the chart shows"):
        plot(fig)
    with detail():            # technical tables and evidence for analysts, collapsed
        ...
"""
from __future__ import annotations

import html
import re

import plotly.graph_objects as go
import streamlit as st

BLUE = "#4318ff"        # indigo: primary series
LIGHT_BLUE = "#39b8ff"  # cyan: second series (pair validated for colour-blind safety; label it, it is light)
NAVY = "#2b3674"
GREY = "#a3aed0"
ICON = {"indigo": "#4318ff", "blue": "#4318ff", "purple": "#7551ff", "teal": "#01b574", "green": "#05cd99",
        "orange": "#ff9b05", "red": "#ee5d50", "yellow": "#ffb547", "grey": "#a3aed0", "cyan": "#39b8ff"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,1,0');
html, body, .stApp, .stMarkdown, .stCaption, button, input, label, textarea, [data-testid="stSidebar"] {
  font-family: "DM Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif !important; }
.stApp, [data-testid="stAppViewContainer"] { background: #f4f7fe; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1480px; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 16px; line-height: 1.6; color: #47548c; }
[data-testid="stMarkdownContainer"] strong { color: #2b3674; }

/* sidebar: white, brand on top, active page in navy with an indigo marker */
[data-testid="stSidebar"] { background: #ffffff; border-right: none; box-shadow: 4px 0 30px rgba(112,144,176,.08); }
[data-testid="stSidebarNav"] a span { font-size: 15px; font-weight: 500; color: #a3aed0; }
[data-testid="stSidebarNav"] a { border-radius: 0; padding-top: 6px; padding-bottom: 6px; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: transparent; box-shadow: inset -4px 0 0 #4318ff; }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: #2b3674; font-weight: 700; }
[data-testid="stSidebarNav"] a:hover { background: #f4f7fe; }
[data-testid="stNavSectionHeader"] { color: #a3aed0; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }

/* page header: breadcrumb, large title, period pill */
.hz-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin: 0 0 18px; }
.hz-crumb { font-size: 14px; color: #707eae; font-weight: 500; }
.hz-title { font-size: 34px; font-weight: 700; color: #2b3674; line-height: 1.15; letter-spacing: -.4px; }
.hz-sub { font-size: 16px; color: #707eae; margin-top: 4px; }
.hz-pill { background: #fff; border-radius: 30px; padding: 10px 18px; box-shadow: 14px 17px 40px 4px rgba(112,144,176,.08);
  display: flex; align-items: center; gap: 8px; color: #2b3674; font-size: 14px; font-weight: 500; white-space: nowrap; }
.hz-pill span.ms { font-family: 'Material Symbols Rounded'; color: #4318ff; font-size: 20px; }

/* headline cards */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 18px; margin: 4px 0 20px; }
.kpi { background: #fff; border-radius: 20px; padding: 16px 18px; display: flex; align-items: center; gap: 14px; min-height: 96px;
  box-shadow: 14px 17px 40px 4px rgba(112,144,176,.08); }
.kpi .i { width: 50px; height: 50px; border-radius: 50%; background: #f4f7fe; display: flex; align-items: center; justify-content: center; flex: 0 0 50px; }
.kpi .i span { font-family: 'Material Symbols Rounded'; font-size: 28px; font-variation-settings: 'FILL' 1; }
.kpi .l { font-size: 14px; color: #a3aed0; font-weight: 500; line-height: 1.25; }
.kpi .v { font-size: 24px; font-weight: 700; color: #2b3674; line-height: 1.25; margin-top: 2px; }
.kpi .n { font-size: 12.5px; color: #a3aed0; margin-top: 2px; }

/* cards, key points, sections */
div[class*="st-key-card_"], div[class*="st-key-points_"] { background: #fff; border: none; border-radius: 20px; padding: 20px 24px 10px;
  box-shadow: 14px 17px 40px 4px rgba(112,144,176,.08); }
.card-t { font-size: 21px; font-weight: 700; color: #2b3674; letter-spacing: -.2px; }
.card-s { font-size: 14px; color: #a3aed0; margin: 2px 0 8px; }
.sec { font-size: 25px; font-weight: 700; color: #2b3674; margin: 28px 0 14px; letter-spacing: -.3px; }
.sec::after { content: ""; display: block; width: 44px; height: 4px; border-radius: 4px; background: #4318ff; margin-top: 6px; }
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 12px; }
.chip { background: #f4f7fe; border-radius: 14px; padding: 8px 14px; }
.chip .cl { font-size: 12.5px; color: #a3aed0; font-weight: 500; }
.chip .cv { font-size: 18px; color: #2b3674; font-weight: 700; }

/* readable tables for the client-facing lists (text wraps) */
.hz-table { width: 100%; border-collapse: collapse; margin: 4px 0 10px; }
.hz-table th { text-align: left; font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: #a3aed0; font-weight: 600;
  padding: 10px 12px; border-bottom: 1px solid #e9edf7; }
.hz-table td { font-size: 15px; color: #2b3674; padding: 11px 12px; border-bottom: 1px solid #f1f3fb; vertical-align: top; line-height: 1.45; }
.hz-table td:first-child { font-weight: 700; white-space: nowrap; }
.hz-badge { display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 13px; font-weight: 600; white-space: nowrap; }

/* collapsible sections and tabs */
[data-testid="stExpander"] details { background: #fff; border: none; border-radius: 16px; box-shadow: 14px 17px 40px 4px rgba(112,144,176,.06); }
[data-testid="stExpander"] summary p { font-size: 16px; font-weight: 700; color: #2b3674; }
[data-testid="stTabs"] button p { font-size: 15px; font-weight: 600; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40] or "x"


def header(title: str, subtitle: str | None = None, chip: str | None = None, crumb: str = "Floor performance review") -> None:
    from common import date_range
    if chip is None:
        s, e = date_range()
        chip = f"{s:%b %-d} – {e:%b %-d, %Y}"
    sub = f'<div class="hz-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="hz-head"><div><div class="hz-crumb">{html.escape(crumb)} / {html.escape(title)}</div>'
                f'<div class="hz-title">{html.escape(title)}</div>{sub}</div>'
                f'<div class="hz-pill"><span class="ms">calendar_month</span>{html.escape(chip)}</div></div>', unsafe_allow_html=True)


def tile(label: str, value: str, note: str = "", icon: str = "insights", color: str = "indigo") -> dict:
    return {"label": label, "value": value, "note": note, "icon": icon, "color": color}


def kpis(tiles: list[dict]) -> None:
    parts = []
    for t in tiles:
        c = ICON.get(t["color"], ICON["indigo"])
        note = f'<div class="n">{html.escape(t["note"])}</div>' if t["note"] else ""
        parts.append(f'<div class="kpi"><div class="i"><span style="color:{c}">{t["icon"]}</span></div><div>'
                     f'<div class="l">{html.escape(t["label"])}</div><div class="v">{html.escape(t["value"])}</div>{note}</div></div>')
    st.markdown(f'<div class="kpi-row">{"".join(parts)}</div>', unsafe_allow_html=True)


def chips(items: list[tuple[str, str]]) -> None:
    """A compact row of label/value facts inside a card (e.g. cost, expected benefit, range)."""
    body = "".join(f'<div class="chip"><div class="cl">{html.escape(l)}</div><div class="cv">{html.escape(v)}</div></div>' for l, v in items)
    st.markdown(f'<div class="chips">{body}</div>', unsafe_allow_html=True)


BADGE = {"Machine under-performs": ("#fff4e5", "#c26a00"), "Inspect payout settings": ("#fdecea", "#c0392b"),
         "Location": ("#efeaff", "#4318ff"), "Game keeps less per wager": ("#e6f8f1", "#01845a"),
         "Too little data": ("#f1f3f8", "#707eae"), "Chance (luck)": ("#f1f3f8", "#707eae"), "No concern": ("#e6f8f1", "#01845a")}


def html_table(df, badge_col: str | None = None) -> None:
    """A readable table for short client-facing lists: wrapped text, larger font, coloured finding badges."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = html.escape(str(r[c]))
            if c == badge_col:
                bg, fg = BADGE.get(str(r[c]), ("#f1f3f8", "#2b3674"))
                v = f'<span class="hz-badge" style="background:{bg};color:{fg}">{v}</span>'
            cells.append(f"<td>{v}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    st.markdown(f'<table class="hz-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>', unsafe_allow_html=True)


def card(title: str, subtitle: str | None = None, key: str | None = None):
    box = st.container(key=f"card_{key or _slug(title)}")
    sub = f'<div class="card-s">{html.escape(subtitle)}</div>' if subtitle else ""
    box.markdown(f'<div class="card-t">{html.escape(title)}</div>{sub}', unsafe_allow_html=True)
    return box


def key_points(points: list[str], more: str | None = None, title: str = "Key points", key: str = "main") -> None:
    """Short bullet summary in a card, with the full explanation collapsed underneath."""
    with st.container(key=f"points_{key}"):
        st.markdown(f'<div class="card-t">{html.escape(title)}</div>', unsafe_allow_html=True)
        st.markdown("\n".join(f"- {p}" for p in points))
        if more:
            with st.expander("Read the full explanation"):
                st.markdown(more)


def summary(text: str, key: str = "main") -> None:
    """A short paragraph in a card (used where a list does not fit)."""
    with st.container(key=f"points_{key}"):
        st.markdown(text)


def section(title: str) -> None:
    st.markdown(f'<div class="sec">{html.escape(title)}</div>', unsafe_allow_html=True)


def detail(label: str = "Technical detail (for analysts)"):
    return st.expander(label)


def plot(fig: go.Figure, height: int | None = None, key: str | None = None, legend_top: bool = False) -> None:
    """Card-style chart: the card shows the title, so the chart's own title is removed."""
    fig.update_layout(title={"text": "", "subtitle": {"text": ""}}, paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      font={"family": "DM Sans, Segoe UI, Arial, sans-serif", "size": 12.5, "color": "#707eae"},
                      margin={"t": 34 if legend_top else 12, "b": 40, "l": 8, "r": 12}, barcornerradius=6,
                      hoverlabel={"font": {"family": "DM Sans, Segoe UI, Arial, sans-serif"}})
    if legend_top:
        fig.update_layout(legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "xanchor": "left"})
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(gridcolor="#eef1fa", linecolor="#e9edf7", automargin=True, tickfont={"color": "#a3aed0"})
    fig.update_yaxes(gridcolor="#eef1fa", linecolor="#e9edf7", automargin=True, tickfont={"color": "#707eae"})
    st.plotly_chart(fig, width="stretch", key=key, theme=None, config={"displaylogo": False, "displayModeBar": False})
