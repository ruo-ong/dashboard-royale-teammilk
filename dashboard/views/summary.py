"""Summary and recommendation: the decision, in plain language, readable in a minute."""
import streamlit as st

from common import PLAIN_ADVICE, PLAIN_VERDICT, evidence, money, out, page_link, pct, table
from ui import card, detail, header, kpis, section, summary, tile


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"]
    kept = pf["kept_usd"].dropna().iloc[0]
    comp = out("a9_list_comparison")
    v = out("machine_verdicts")
    ten = v[v["in_manager_10"]]
    counts = ten["verdict"].value_counts()
    stays = int((comp["status"] == "stays").sum())

    header("Review of the Proposed Machine Replacements",
           "Summary of findings and recommended use of the $100,000 operating budget for July 1–30, 2025",
           chip="Records reviewed: Jan 1 – Jun 30, 2025")
    summary(
        "Management proposed to replace the ten machines that earned the least between January 1 and June 30, 2025. "
        "Before any machine is replaced, we examined whether each machine's low earnings were caused by the machine itself "
        "or by other circumstances: ordinary variation in results from chance (\"luck\"), its position on the casino floor, "
        "time spent out of service, or the date on which it was installed or removed.\n\n"
        f"Our review indicates that **only {stays} of the ten machines** (M-1179) performs poorly for reasons that can be "
        "attributed to the machine. Most of the others are located in the Back Forty, the area of the floor with the lowest level "
        "of play, or run a game that by design keeps a smaller share of each wager. One machine (M-1158) pays out in a pattern "
        "that does not match its published settings and should be inspected before any other decision is made.\n\n"
        f"We therefore do not recommend replacing the ten machines as proposed. We recommend the three actions listed below, at a "
        f"total cost of **{money(funded['cost'].sum())}**, and that the remaining **{money(kept)}** be retained.")

    kpis([tile("Machines on the proposed list", "10", "lowest earnings, Jan–Jun", "list_alt", "blue"),
          tile("Recommended for replacement", f"{stays} of 10", "machine itself is the cause", "swap_horiz", "orange"),
          tile("Recommended spending", money(funded["cost"].sum()), f"{len(funded)} actions", "payments", "purple"),
          tile("Expected net benefit", money(pf["net_mid"].sum()), "expected win, July 1–30", "trending_up", "green"),
          tile("Budget retained", money(kept), "of $100,000", "savings", "teal")])

    section("Recommended actions for July 1–30, 2025")
    for r in funded.itertuples():
        with card(f"{r.name} (quantity {r.quantity}) · cost {money(r.cost)}", key=f"act_{r.action_type_id}"):
            st.markdown(f"Expected benefit: **{money(r.mid)}** in expected win over the month, within an estimated range of "
                        f"{money(r.low)} to {money(r.high)}. Applies to: {r.targets}.")
    page_link("plan", "Read the full plan, including costs, uncertainty and how results will be measured")

    section("How each machine on the proposed list was assessed")
    reasons = {"Location": "its position on the floor", "Low-hold game": "a game that keeps a smaller share of each wager by design",
               "Watch list": "too little time on the floor to judge", "Inspect": "a payout pattern that requires inspection",
               "Truly weak": "the machine itself", "Unlucky": "chance", "Short time on floor": "a short time on the floor"}
    st.markdown("Of the ten machines, the main cause of low earnings was: " + "; ".join(
        f"**{reasons.get(k, k.lower())}** for {n}" for k, n in counts.items()) + ".")
    show = comp[comp["status"] != "new"].assign(Finding=lambda d: d["verdict"].map(PLAIN_VERDICT),
                                                 Recommendation=lambda d: d["verdict"].map(PLAIN_ADVICE)).rename(columns={"machine_id": "Machine"})
    table(show[["Machine", "Finding", "Recommendation"]], column_config={"Recommendation": st.column_config.TextColumn(width="large")})
    page_link("machines", "Read the machine review")

    section("Other findings")
    st.markdown(
        "- **Demand.** Business across the floor was broadly stable over the six months and moved with Las Vegas visitor numbers. "
        "The largest local change was the temporary closure of the walkway to the Back Forty (March 3 to April 6), during which "
        "play in that area fell by about one third.\n"
        "- **Downtime.** Machines were out of service for 5,021 hours in total, which cost an estimated $103,000 in expected win "
        "over six months. Faults were repaired fastest when two technicians were on duty.\n"
        f"- **Loyalty members.** {pct(out('d2_overview')['share_players_ahead'].iloc[0])} of members who played on a card finished "
        "the period ahead. Results are concentrated among a small share of frequent players.\n"
        "- **Loyalty rewards.** On May 1 the number of points needed per reward dollar was reduced by more than half for all members. "
        "It is not yet possible to say whether this change has paid for itself.")
    with detail():
        st.markdown("The full comparison between the proposed list and ours, with the reasoning for each machine:")
        table(comp.rename(columns={"machine_id": "Machine", "status": "Status", "verdict": "Verdict", "why": "Why", "advice": "Advice"}),
              column_config={"Why": st.column_config.TextColumn(width="large")})
        for cid in ["A8-01", "A4-01", "B9-03", "A9-01", "R-01"]:
            evidence(cid)
