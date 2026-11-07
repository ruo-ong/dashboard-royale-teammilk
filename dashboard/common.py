"""Shared pieces for every dashboard page: cached data, filters, formatting, evidence links.

The dashboard reads only outputs/ (built by `python -m tasks.run_all`). The machine-trial page recomputes its
tables live from outputs/machine_day_base for the chosen date range, using the same compute() functions as the
task scripts, so the numbers always match.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from royale.charts import COLORS, SEQUENTIAL_BLUE, style  # noqa: E402,F401
from royale.outputs import read_output  # noqa: E402

WINDOW = (dt.date(2025, 1, 1), dt.date(2025, 6, 30))
PAGES: dict[str, st.Page] = {}   # filled by app.py so pages can link to each other


# ---------------- data ----------------
@st.cache_data(show_spinner=False)
def out(name: str) -> pd.DataFrame:
    return read_output(name)


@st.cache_data(show_spinner=False)
def claims() -> pd.DataFrame:
    return pd.read_csv(ROOT / "docs" / "claims_log.csv").fillna("")


# ---------------- filters ----------------
def date_range() -> tuple[dt.date, dt.date]:
    return st.session_state.get("date_range", WINDOW)


def is_full_window() -> bool:
    return tuple(date_range()) == WINDOW


def zone_bank_filter(df: pd.DataFrame, zone_col: str = "zone_name", bank_col: str | None = "bank_id") -> pd.DataFrame:
    zones = st.session_state.get("zones") or []
    banks = st.session_state.get("banks") or []
    if zones and zone_col in df:
        df = df[df[zone_col].isin(zones)]
    if banks and bank_col and bank_col in df:
        df = df[df[bank_col].isin(banks)]
    return df


def filter_note() -> None:
    start, end = date_range()
    parts = [f"{start:%b %-d} – {end:%b %-d, %Y}"]
    if st.session_state.get("zones"):
        parts.append("zones: " + ", ".join(st.session_state["zones"]))
    if st.session_state.get("banks"):
        parts.append("banks: " + ", ".join(st.session_state["banks"]))
    st.caption("Showing " + " · ".join(parts))


# ---------------- formatting ----------------
def money(x: float, digits: int = 0, signed: bool = False) -> str:
    if pd.isna(x):
        return "–"
    sign = "−" if x < 0 else ("+" if signed else "")
    a = abs(x)
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.{max(digits, 1)}f}M"
    if a >= 1e4:
        return f"{sign}${a / 1e3:,.{digits}f}k"
    return f"{sign}${a:,.{digits}f}"


def pct(x: float, digits: int = 0, signed: bool = False) -> str:
    return "–" if pd.isna(x) else f"{x:{'+' if signed else ''}.{digits}%}"


def kpi(col, label: str, value: str, note: str | None = None) -> None:
    """A headline number with an optional plain note (st.metric's delta would draw a misleading up/down arrow)."""
    with col:
        st.metric(label, value)
        if note:
            st.caption(note)


def chart(fig: go.Figure, key: str | None = None) -> None:
    # theme=None: keep our own layout (Streamlit's theme overrides margins and clips the titles)
    st.plotly_chart(fig, width="stretch", key=key, theme=None, config={"displaylogo": False, "displayModeBar": False})


def table(df: pd.DataFrame, **kwargs) -> None:
    st.dataframe(df, width="stretch", hide_index=True, **kwargs)


def page_link(name: str, label: str) -> None:
    if name in PAGES:
        st.page_link(PAGES[name], label=label, icon=":material/arrow_forward:")


# ---------------- evidence ----------------
def evidence(ids: str | list[str], label: str = "Evidence") -> None:
    """Expandable panel tracing claim IDs to table/query -> result -> alternative tested -> limitation (judge task 4)."""
    ids = [i.strip() for i in (ids.split(",") if isinstance(ids, str) else ids) if i and i.strip()]
    log = claims().set_index("claim_id")
    found = [i for i in ids if i in log.index]
    if not found:
        return
    with st.expander(f"{label}: {', '.join(found)}"):
        for i in found:
            c = log.loc[i]
            st.markdown(f"**{i}** · {c['claim']}")
            st.markdown(f"- **Table / query:** `{c['table_query']}`\n- **Result:** {c['result']}\n"
                        f"- **Alternative tested:** {c['alternative_tested']}\n- **Limitation:** {c['limitation']}\n"
                        f"- **Status:** {c['status']} · **Where:** {c['dashboard_location']}")


def tracked_label() -> None:
    st.info("Player numbers cover **tracked (loyalty-card) play only**. Uncarded play is invisible at the person level, "
            "so totals here never match the machine meters, and that is expected.", icon=":material/badge:")
