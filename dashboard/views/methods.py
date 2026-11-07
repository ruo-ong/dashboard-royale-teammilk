"""Methods and evidence: terms used in the report, how the figures were produced, limitations, and the full evidence log."""
import streamlit as st

from common import ROOT, claims, table
from ui import card, header, key_points, summary

TERMS = [
    ("Amount wagered (coin-in)", "The total value of all bets placed on a machine, including winnings that were bet again."),
    ("Payout", "The amount the machines paid back to players."),
    ("House win", "The amount the casino actually kept: the amount wagered minus payouts. It includes the effect of luck and can be negative on a given day."),
    ("Payback percentage", "The long-run share of wagers a game is designed to return to players (for example, 95%). The remainder is the share the casino expects to keep."),
    ("Expected win (theo)", "What the casino would expect to keep from the wagers placed, given each game's payback percentage. Because it removes luck, it is the fairest measure of how much play a machine attracts."),
    ("Expected win per available hour", "Expected win divided by the hours the machine was in working order. It allows fair comparison between machines that were on the floor for different lengths of time or were out of service."),
    ("Luck", "The difference between what the casino actually kept and what it expected to keep. Within two standard deviations of zero, the difference is considered normal variation."),
    ("Availability", "The share of time a machine was in working order while installed."),
    ("Occupancy", "The share of working time during which a player was seated at the machine."),
    ("Bank of machines", "A group of five to eight machines installed together. A machine's neighbours are the other machines in its bank."),
    ("Loyalty member play (tracked play)", "Play recorded on a loyalty card. Play without a card cannot be linked to a person."),
    ("Rewards (comps)", "Complimentary food and drink that members obtain with loyalty points. Their cost is the cost of the goods."),
    ("Contribution after supplied costs", "House win minus the machine costs provided in the data (lease, service, power, repairs). It does not include rent, taxes or full staffing."),
]

LIMITS = [
    "The Gilded Ace is a fictional casino and its records are synthetic. Only the tourism, weather and Missouri figures are real public data; no finding concerns a real casino.",
    "Days before a machine was installed or after it was removed (1,018 machine-days) are excluded; they are not treated as days with no play.",
    "Rates are calculated from totals (for example, total house win divided by total wagered), not as averages of daily rates.",
    "Figures for loyalty members cover card play only and will not match the machine totals.",
    "Door counters count entries, not individual people. Hours when a counter was offline are treated as missing.",
    "Unusual payout patterns are reasons to inspect a machine. They are not evidence of wrongdoing.",
    "The forecast uses only information available on April 30. Tourism and survey data are published later and are not used as forecast inputs.",
    "Thresholds used to classify machines (for example, 0.7 times the neighbouring machines' level) are starting values and can be adjusted.",
]


def render() -> None:
    header("Methods and Evidence", "Terms used in this report, how the figures were produced, their limitations, and the evidence log",
           chip="Reference")
    more_text = (
        "Every figure in this report is calculated by code kept with the report, from the records supplied for January 1 to "
        "June 30, 2025. The calculations are checked automatically: totals are reconciled with the source records, the forecast is "
        "checked for any use of information that would not have been available at the time, and the budget plan is checked against "
        "the price list and its limits.\n\n"
        "Each finding in the report is recorded in an evidence log, which states the data used, the result, the alternative "
        "explanations that were considered and the limitations. The log is reproduced in full below.")
    key_points([
        "Every figure is calculated by code kept with this report, from the records for **January 1 – June 30, 2025**.",
        "Totals are **reconciled automatically** with the source records.",
        "The forecast is checked for any use of information **not available at the time**.",
        "Each finding is recorded in the **evidence log** below, with its data, result, alternatives considered and limitations."
    ], more=more_text)
    t1, t2, t3, t4 = st.tabs(["Terms used in this report", "Limitations", "Evidence log", "How to reproduce, and use of AI"])
    with t1:
        for term, meaning in TERMS:
            st.markdown(f"**{term}.** {meaning}")
    with t2:
        for item in LIMITS:
            st.markdown(f"- {item}")
    with t3:
        log = claims()
        q = st.text_input("Search the evidence log", placeholder="For example: M-1158, closure, rewards")
        if q:
            log = log[log.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)]
        st.caption(f"{len(log)} entries. Each entry gives the table or query, the result, the alternative explanation tested and the limitation.")
        table(log, height=560)
        st.download_button("Download the evidence log (CSV)", (ROOT / "docs" / "claims_log.csv").read_bytes(), "claims_log.csv", "text/csv")
        with st.expander("Metric definitions used in the calculations (docs/METRICS.md)"):
            st.markdown((ROOT / "docs" / "METRICS.md").read_text())
    with t4:
        st.markdown(
            "**Use of AI.** The team used Claude (Anthropic), through Claude Code, to help plan the work, write and test the analysis "
            "code and this report, and draft text. All figures are produced by the code in the repository from the challenge data, "
            "checked by automated tests, and reviewed by the team. Each team member records their own use in the appendix.")
        st.markdown(
            "**Reproducing the report.** All code, data and tests are in the repository: "
            "[github.com/ruo-ong/dashboard-royale-teammilk](https://github.com/ruo-ong/dashboard-royale-teammilk). "
            "From the repository folder:\n```sh\npip install -r requirements.txt\npython -m tasks.run_all\n"
            "pytest -q\nstreamlit run dashboard/app.py\n```")
