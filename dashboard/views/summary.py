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
    review = comp.loc[comp["status"] == "review", "machine_id"].tolist()
    a8 = out("a8_decomposition")
    a8 = a8[a8["in_manager_10"]]
    by_piece = a8.groupby("piece")["usd"].sum()
    loc_share = by_piece.get("Location", 0) / a8.drop_duplicates("machine_id")["gap_usd"].sum()
    weak_txt = (f"Only **{stays} of the 10** machines is clearly weak because of the machine itself" if stays else
                "**None of the 10** machines is clearly weak because of the machine itself")
    review_txt = (f"; **{', '.join(review)}** is borderline and should be reviewed again" if review else "")
    pf_info = funded["info"].sum() if "info" in funded else 0.0

    header("Summary and Recommendation",
           "Summary of findings and recommended use of the $100,000 operating budget for July 1–30, 2025",
           chip="Records reviewed: Jan 1 – Jun 30, 2025")
    kpis([tile("Clearly weak machines", f"{stays} of 10", f"borderline: {', '.join(review) or 'none'}", "swap_horiz", "orange"),
          tile("Recommended spending", money(funded["cost"].sum()), f"{len(funded)} actions", "payments", "purple"),
          tile("Expected net benefit", money(pf["net_mid"].sum()), "expected win, July 1–30", "trending_up", "green"),
          tile("Budget retained", money(kept), "of $100,000", "savings", "teal")])
    key_points([
        weak_txt + review_txt + ".",
        f"**Location** is the largest single cause, at **{pct(loc_share)}** of the shortfall; nine of the ten stand in the **Back Forty**, the quietest area.",
        "**Comet Cash** is the one game played less than its neighbours in both halves of the year: review the title, not single machines.",
        "**M-1158** pays out differently from its published settings and should be **inspected first**.",
        (lambda sc: f"Across the **whole floor**, only **{(sc['status'] == 'Underperforms').sum()} of {(sc['status'] != 'Too little data').sum()}** "
                    f"machines consistently earn more than 10% below what their location, game and maker should bring "
                    f"({', '.join(sc.loc[sc['status'] == 'Underperforms', 'machine_id'])}); see Underperforming machines.")(out("a12_floor_screen")),
        f"We recommend **three actions** costing **{money(funded['cost'].sum())}**, and retaining **{money(kept)}**.",
    ], title="Our recommendation", more=(
        "Management proposed to replace the ten machines that earned the least between January 1 and June 30, 2025. "
        "Before any machine is replaced, we examined whether each machine's low earnings were caused by the machine itself "
        "or by other circumstances: ordinary variation in results from chance (\"luck\"), its position on the casino floor, "
        "time spent out of service, or the date on which it was installed or removed.\n\n"
        f"Our review indicates that {'only ' + str(stays) if stays else 'none'} of the ten machines clearly performs poorly for reasons "
        "that can be attributed to the machine itself" + (f"; {', '.join(review)} is close to our threshold and should be reviewed again" if review else "") + ". "
        "Most of the others are located in the Back Forty, the area of the floor with the lowest level "
        "of play, or run a game that by design keeps a smaller share of each wager. One machine (M-1158) pays out in a pattern "
        "that does not match its published settings and should be inspected before any other decision is made. At the level of "
        "game titles, Comet Cash is played less than neighbouring machines in both halves of the year, so its title should be reviewed.\n\n"
        f"We therefore do not recommend replacing the ten machines as proposed. We recommend three actions, at a total cost of "
        f"{money(funded['cost'].sum())}, and that the remaining {money(kept)} be retained."))

    section("Recommended actions, July 1–30")
    short = {"A-INSPECT": "Inspect machine M-1158", "A-MOVE-MACHINE": "Move three Back Forty machines", "A-PROMO": "Hold one promotion weekend",
             "A-COMP-PILOT": "Run a rewards trial"}
    cols = st.columns(len(funded))
    for col, (i, r) in zip(cols, enumerate(funded.itertuples(), start=1)):
        with col:
            with card(f"{i}. {short.get(r.action_type_id, r.name)}", key=f"act_{r.action_type_id}"):
                facts = [("Cost", money(r.cost))]
                facts += [("July benefit", money(r.mid))] if r.mid > 0 else []
                facts += [("Value after July", money(r.info))] if r.info > 0 else []
                chips(facts)
                lines = [f"July range: {money(r.low)} to {money(r.high)}"] if r.mid > 0 else []
                lines += [f"Value of what we learn: {money(r.info_low)} to {money(r.info_high)}"] if r.info > 0 else []
                st.markdown("\n".join(f"- {x}" for x in lines))
    page_link("plan", "Read the full plan, including costs, uncertainty and how results will be measured")

    section("The ten machines on the proposed list")
    reasons = {"Borderline": "a borderline result (review again)", "Location": "its position on the floor", "Low-hold game": "a game that keeps a smaller share of each wager by design",
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
            "- **Rewards:** points needed per reward dollar were cut by more than half on May 1. That raised the potential cost of points "
            f"members already hold by up to {money(out('e3_points_liability')['extra_cost_if_all_redeemed_usd'].iloc[0])}; a trial will show whether the change pays.")
    with detail():
        st.markdown("The full comparison between the proposed list and ours, with the reasoning for each machine:")
        table(comp.rename(columns={"machine_id": "Machine", "status": "Status", "verdict": "Verdict", "why": "Why", "advice": "Advice"}),
              column_config={"Why": st.column_config.TextColumn(width="large")})
        for cid in ["A8-01", "A4-01", "B9-03", "A9-01", "R-01"]:
            evidence(cid)
