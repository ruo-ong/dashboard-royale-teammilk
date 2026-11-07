"""Summary and recommendation: the decision, in plain language, readable in a minute."""
import streamlit as st

from common import PLAIN_ADVICE, PLAIN_VERDICT, evidence, money, out, page_link, pct, table
from ui import card, chips, detail, header, html_table, key_points, kpis, section, tile


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"]
    kept = pf["kept_usd"].dropna().iloc[0]
    comp = out("a9_list_comparison")
    v = out("machine_verdicts")
    ten = v[v["in_manager_10"]]
    counts = ten["verdict"].value_counts()
    stays = int((comp["status"] == "stays").sum())

    header("Summary and Recommendation",
           "Summary of findings and recommended use of the $100,000 operating budget for July 1–30, 2025",
           chip="Records reviewed: Jan 1 – Jun 30, 2025")
    kpis([tile("Recommended for replacement", f"{stays} of 10", "machine itself is the cause", "swap_horiz", "orange"),
          tile("Recommended spending", money(funded["cost"].sum()), f"{len(funded)} actions", "payments", "purple"),
          tile("Expected net benefit", money(pf["net_mid"].sum()), "expected win, July 1–30", "trending_up", "green"),
          tile("Budget retained", money(kept), "of $100,000", "savings", "teal")])
    key_points([
        f"Only **{stays} of the 10** machines on the proposed list should be considered for replacement (M-1179).",
        "**Location** explains most of the shortfall: nine of the ten stand in the **Back Forty**, the quietest area.",
        "**M-1158** pays out differently from its published settings and should be **inspected first**.",
        f"We recommend **three actions** costing **{money(funded['cost'].sum())}**, and retaining **{money(kept)}**.",
    ], title="Our recommendation", more=(
        "Management proposed to replace the ten machines that earned the least between January 1 and June 30, 2025. "
        "Before any machine is replaced, we examined whether each machine's low earnings were caused by the machine itself "
        "or by other circumstances: ordinary variation in results from chance (\"luck\"), its position on the casino floor, "
        "time spent out of service, or the date on which it was installed or removed.\n\n"
        f"Our review indicates that only {stays} of the ten machines (M-1179) performs poorly for reasons that can be "
        "attributed to the machine. Most of the others are located in the Back Forty, the area of the floor with the lowest level "
        "of play, or run a game that by design keeps a smaller share of each wager. One machine (M-1158) pays out in a pattern "
        "that does not match its published settings and should be inspected before any other decision is made.\n\n"
        f"We therefore do not recommend replacing the ten machines as proposed. We recommend three actions, at a total cost of "
        f"{money(funded['cost'].sum())}, and that the remaining {money(kept)} be retained."))

    section("Recommended actions, July 1–30")
    short = {"A-INSPECT": "Inspect machine M-1158", "A-MOVE-MACHINE": "Move three Back Forty machines", "A-PROMO": "Hold two promotion weekends"}
    cols = st.columns(len(funded))
    for col, (i, r) in zip(cols, enumerate(funded.itertuples(), start=1)):
        with col:
            with card(f"{i}. {short.get(r.action_type_id, r.name)}", key=f"act_{r.action_type_id}"):
                chips([("Cost", money(r.cost)), ("Most likely benefit", money(r.mid))])
                st.markdown(f"- Range: {money(r.low)} to {money(r.high)}")
    page_link("plan", "Read the full plan, including costs, uncertainty and how results will be measured")

    section("The ten machines on the proposed list")
    reasons = {"Location": "its position on the floor", "Low-hold game": "a game that keeps a smaller share of each wager by design",
               "Watch list": "too little time on the floor to judge", "Inspect": "a payout pattern that requires inspection",
               "Truly weak": "the machine itself", "Unlucky": "chance", "Short time on floor": "a short time on the floor"}
    st.markdown("**Main cause of low earnings:**\n" + "\n".join(f"- {reasons.get(k, k.lower()).capitalize()}: **{n}** machine{'s' if n > 1 else ''}" for k, n in counts.items()))
    show = comp[comp["status"] != "new"].assign(Finding=lambda d: d["verdict"].map(PLAIN_VERDICT),
                                                 Recommendation=lambda d: d["verdict"].map(PLAIN_ADVICE)).rename(columns={"machine_id": "Machine"})
    with card("Finding for each machine", key="ten_table"):
        html_table(show[["Machine", "Finding", "Recommendation"]], badge_col="Finding")
    page_link("machines", "Read the machine review")

    section("Other findings")
    with card("At a glance", key="other_findings"):
        st.markdown(
            "- **Demand:** stable, and in line with Las Vegas visitor numbers. The Back Forty walkway closure (Mar 3 – Apr 6) cut play there by about a third.\n"
            "- **Downtime:** 5,021 machine-hours out of service, about $103,000 of expected win. Repairs are fastest with two technicians on duty.\n"
            f"- **Loyalty members:** {pct(out('d2_overview')['share_players_ahead'].iloc[0])} finished ahead. Results are concentrated among frequent players.\n"
            "- **Rewards:** points needed per reward dollar were cut by more than half on May 1. It is too early to say whether this paid for itself.")
    with detail():
        st.markdown("The full comparison between the proposed list and ours, with the reasoning for each machine:")
        table(comp.rename(columns={"machine_id": "Machine", "status": "Status", "verdict": "Verdict", "why": "Why", "advice": "Advice"}),
              column_config={"Why": st.column_config.TextColumn(width="large")})
        for cid in ["A8-01", "A4-01", "B9-03", "A9-01", "R-01"]:
            evidence(cid)
