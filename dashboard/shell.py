"""App shell: page setup, sidebar brand, navigation and filters, and the first-run build of outputs/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import common  # noqa: E402
import ui  # noqa: E402


def run(include_estimator: bool = True) -> None:
    st.set_page_config(page_title="The Gilded Ace: Floor Performance Review", page_icon=":material/casino:", layout="wide")
    ui.inject_css()
    st.logo(str(Path(__file__).resolve().parent / "assets" / "logo.svg"), size="large")
    from tasks import run_all
    if not run_all.is_complete():
        with st.spinner("Preparing the report from the source data. The first visit takes about one minute."):
            os.environ["ROYALE_NO_PNG"] = "1"
            run_all.run(force=False)   # one build at a time; a session that waited simply finds the outputs ready
            st.cache_data.clear()

    from views import comps, demand, downtime, machines, methods, model, plan, players, summary
    pages = {
        "summary": st.Page(summary.render, title="Summary", icon=":material/description:", default=True),
        "plan": st.Page(plan.render, title="Recommended actions", icon=":material/payments:", url_path="plan"),
        "machines": st.Page(machines.render, title="Machine review", icon=":material/fact_check:", url_path="machines"),
        "demand": st.Page(demand.render, title="Visitor demand", icon=":material/trending_up:", url_path="demand"),
        "downtime": st.Page(downtime.render, title="Machine downtime", icon=":material/build:", url_path="downtime"),
        "players": st.Page(players.render, title="Loyalty members", icon=":material/group:", url_path="players"),
        "comps": st.Page(comps.render, title="Loyalty rewards", icon=":material/redeem:", url_path="comps"),
        "model": st.Page(model.render, title="Business forecast", icon=":material/query_stats:", url_path="forecast"),
        "methods": st.Page(methods.render, title="Methods and evidence", icon=":material/menu_book:", url_path="methods"),
    }
    groups = {"Overview": [pages["summary"], pages["plan"]],
              "Findings": [pages["machines"], pages["demand"], pages["downtime"], pages["players"], pages["comps"]]}
    if include_estimator:
        from views import estimator
        pages["estimator"] = st.Page(estimator.render, title="Machine estimator", icon=":material/calculate:", url_path="estimator")
        groups["Tools"] = [pages["estimator"]]
    groups["Supporting material"] = [pages["model"], pages["methods"]]
    common.PAGES.update(pages)
    nav = st.navigation(groups)

    with st.sidebar:
        st.markdown("### Filters")
        picked = st.date_input("Period under review", value=common.WINDOW, min_value=common.WINDOW[0], max_value=common.WINDOW[1],
                               help="The machine review, demand and downtime pages are recalculated for this period. "
                                    "The forecast page always uses its fixed test period, as explained on that page.")
        st.session_state["date_range"] = (picked[0], picked[1]) if isinstance(picked, (tuple, list)) and len(picked) == 2 else common.WINDOW
        banks = common.out("bank_scores")
        st.session_state["zones"] = st.multiselect("Floor zone", sorted(banks["zone_name"].unique()), key="zone_select")
        choices = banks[banks["zone_name"].isin(st.session_state["zones"])] if st.session_state["zones"] else banks
        st.session_state["banks"] = st.multiselect("Bank of machines", sorted(choices["bank_id"]), key="bank_select")
        st.divider()
        st.caption("The Gilded Ace is a fictional casino and its records are synthetic. Las Vegas tourism, weather and Missouri "
                   "figures are real public data. Prepared by Team Milk for the TAMU Datathon (Dashboard Royale)."
)
    nav.run()
