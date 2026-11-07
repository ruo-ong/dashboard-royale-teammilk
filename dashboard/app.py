"""Team Milk dashboard: The Gilded Ace, "Luck, Location, or a Leak?"

Run from the repo root:   streamlit run dashboard/app.py
If outputs/ is empty (first run, or a fresh deploy) it builds them first (about a minute).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from royale.outputs import output_path  # noqa: E402
from views import comps, demand, downtime, machines, methods, model, plan, players, summary  # noqa: E402

st.set_page_config(page_title="Gilded Ace: Luck, Location, or a Leak?", page_icon=":material/casino:", layout="wide")

if not output_path("portfolio").exists():
    with st.spinner("First run: building every analysis table from the raw data (about a minute)..."):
        os.environ["ROYALE_NO_PNG"] = "1"
        from tasks.run_all import run
        run()
        st.cache_data.clear()

pages = {
    "summary": st.Page(summary.render, title="Summary: the decision", icon=":material/flag:", default=True),
    "machines": st.Page(machines.render, title="Q1 · The machine trial", icon=":material/gavel:", url_path="machines"),
    "demand": st.Page(demand.render, title="Q2 · Demand", icon=":material/trending_up:", url_path="demand"),
    "downtime": st.Page(downtime.render, title="Q3 · Downtime", icon=":material/build:", url_path="downtime"),
    "players": st.Page(players.render, title="Q4 · Tracked players", icon=":material/group:", url_path="players"),
    "comps": st.Page(comps.render, title="Q5 · Comps", icon=":material/redeem:", url_path="comps"),
    "model": st.Page(model.render, title="Forecast model", icon=":material/query_stats:", url_path="model"),
    "plan": st.Page(plan.render, title="Q6 · The $100k plan", icon=":material/payments:", url_path="plan"),
    "methods": st.Page(methods.render, title="Methods, claims & notes", icon=":material/menu_book:", url_path="methods"),
}
common.PAGES.update(pages)
nav = st.navigation({"Decision": [pages["summary"], pages["plan"]],
                     "The six questions": [pages["machines"], pages["demand"], pages["downtime"], pages["players"], pages["comps"]],
                     "How we know": [pages["model"], pages["methods"]]})

with st.sidebar:
    st.markdown("### Filters")
    picked = st.date_input("Analysis period", value=common.WINDOW, min_value=common.WINDOW[0], max_value=common.WINDOW[1],
                           help="Machine trial, demand and downtime pages recompute for this period. The model page is fixed (see why on that page).")
    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        st.session_state["date_range"] = (picked[0], picked[1])
    else:
        st.session_state["date_range"] = common.WINDOW
    banks = common.out("bank_scores")
    st.session_state["zones"] = st.multiselect("Zone", sorted(banks["zone_name"].unique()), key="zone_select")
    choices = banks[banks["zone_name"].isin(st.session_state["zones"])] if st.session_state["zones"] else banks
    st.session_state["banks"] = st.multiselect("Bank", sorted(choices["bank_id"]), key="bank_select")
    st.divider()
    st.caption("The Gilded Ace is fictional and its data synthetic; tourism, weather and Missouri benchmarks are real public data. "
               "Built by Team Milk for TAMU Datathon · Dashboard Royale.")

nav.run()
