"""W10 - methods, caveats, the claims & evidence log, and the AI-use disclosure."""
import streamlit as st

from common import ROOT, claims, table


CAVEATS = [
    "The Gilded Ace is fictional and its data synthetic; only `4_context/real_sources/` is real public data. No finding is about a real casino.",
    "Off-floor machine-days (1,018: before install or after retirement) are excluded everywhere; they are not zero sales.",
    "Every ratio is a ratio of sums (e.g. hold = Σ house win ÷ Σ coin-in), never an average of daily ratios.",
    "Money: `_cents` columns are converted to dollars once, in the base table. March 8 has 23 hours; hours come from `scheduled_seconds`.",
    "Player, trip, session and comp numbers are **tracked (loyalty-card) play only** and never match machine meters.",
    "Comp cost is inside POS cost of goods and is subtracted once.",
    "Door counters count entries, not people; offline hours are missing, never zero; low-coverage days are left out of comparisons.",
    "Demand and benefits use theo (expected win); house win contains luck. Supplied costs are partial: 'contribution after supplied costs'.",
    "Unusual payout patterns are inspection leads, never accusations.",
    "The forecast uses a time split only, with inputs known on April 30; tourism and survey data are published later and are not inputs.",
    "Thresholds (luck/hit-rate z cut-offs, peer index 0.7, volume 0.8, 60 days) are starting values to be locked by the team.",
]


def render() -> None:
    st.title("Methods, claims & notes")
    t1, t2, t3, t4 = st.tabs(["Claims & evidence log", "Metric definitions", "Caveats", "AI use & reproducibility"])
    with t1:
        log = claims()
        q = st.text_input("Search claims", placeholder="e.g. M-1158, closure, comp")
        if q:
            log = log[log.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)]
        st.caption(f"{len(log)} claims. Each: table/query → result → alternative explanation tested → limitation.")
        table(log, height=600)
        st.download_button("Download the claims log (CSV)", (ROOT / "docs" / "claims_log.csv").read_bytes(), "claims_log.csv", "text/csv")
    with t2:
        st.markdown((ROOT / "docs" / "METRICS.md").read_text())
    with t3:
        for c in CAVEATS:
            st.markdown(f"- {c}")
    with t4:
        st.markdown(
            "**AI-use disclosure.** We used Claude (Anthropic) through Claude Code to plan the work, write and test the analysis "
            "code and this dashboard, and draft text. Every number on these pages is computed by the code in this repository from "
            "the challenge data, checked by automated tests (reconciliations, leakage rules, budget rules), and reviewed by the team. "
            "Each team member adds their own usage in the appendix.")
        st.markdown(
            "**Reproduce everything.** From the repository folder:\n```sh\npip install -r requirements.txt\npython -m tasks.run_all   "
            "# rebuild every output table (~1 min)\npytest -q                  # all checks\nstreamlit run dashboard/app.py\n```\n"
            "The forecast protocol was committed before any model code: `docs/MODEL_PROTOCOL.md`. "
            "Model write-up: `docs/MODEL.md`.")
