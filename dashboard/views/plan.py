"""Recommended actions: each funded action with its cost, expected benefit, uncertainty, measurement and evidence."""
import plotly.graph_objects as go
import streamlit as st

from common import evidence, money, out, page_link, pct, table
from ui import BLUE, card, detail, header, kpis, plot, section, summary, tile

PAGE_FOR = {"A-PROMO": ("demand", "See the evidence on the visitor demand page"),
            "A-INSPECT": ("machines", "See the evidence on the machine review page"),
            "A-MOVE-MACHINE": ("machines", "See the evidence on the machine review page")}
WHY = {"A-INSPECT": "Machine M-1158 pays out on far more spins than its published settings allow, in every month reviewed. "
                    "An inspection will establish whether its configuration is correct.",
       "A-MOVE-MACHINE": "The Back Forty has the lowest level of play on the floor. Three of its machines can be moved into empty "
                         "positions in busier areas without displacing any other machine.",
       "A-PROMO": "The casino's own promotion weekends have previously raised play by 6% to 18% above comparable days."}
PLAIN = {"A-TECH-SHIFT": "Downtime costs about $17,000 of expected win per month in total, so an additional technician "
                         "(cost $11,520) would recover only a few hundred dollars in July.",
         "A-REPLACE-LEASE": "A leased replacement operates for only 16 of the 30 days after delivery; the expected gain does not "
                            "cover the $3,380 cost per machine within the month.",
         "A-REPLACE-BUY": "A purchased machine costs $22,000 and would operate for only 9 days in July.",
         "A-PREVENTIVE": "The records contain only three scheduled maintenance visits, which is too few to show what maintenance achieves.",
         "A-WAYFINDING": "New signs for the Back Forty may help, but the expected gain ($5,181) is below the cost ($7,500) and is uncertain.",
         "A-COMP-PILOT": "A controlled trial of the rewards rate would answer an open question, but it produces no additional win "
                         "within July and the three action slots are better used elsewhere."}


def range_chart(funded) -> go.Figure:
    f = funded.sort_values("mid")
    fig = go.Figure()
    for r in f.itertuples():
        fig.add_trace(go.Scatter(x=[r.low - r.cost, r.high - r.cost], y=[r.name] * 2, mode="lines",
                                 line={"color": "#bcd4f6", "width": 12}, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f["mid"] - f["cost"], y=f["name"], mode="markers+text", name="Most likely result",
                             marker={"size": 12, "color": BLUE, "symbol": "diamond"},
                             text=[money(v, signed=True) for v in f["mid"] - f["cost"]], textposition="top center",
                             hovertemplate="%{y}<br>most likely net benefit %{x:$,.0f}<extra></extra>"))
    fig.add_vline(x=0, line={"color": "#8a8a8a", "width": 1})
    fig.update_xaxes(tickformat="$,.0f", title_text="Net benefit over July (expected win minus cost)")
    fig.update_yaxes(automargin=True)
    fig.update_layout(height=260, showlegend=False)
    return fig


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"]
    sens = out("r5_sensitivity").set_index("action_type_id")
    meas = out("r6_measurement").set_index("action_type_id")
    kept = pf["kept_usd"].dropna().iloc[0]

    header("Recommended Actions", "Use of the $100,000 operating budget for July 1–30, 2025", chip="Budget period: Jul 1 – Jul 30, 2025")
    summary(
        "Each action below addresses a cause identified in this review. Costs follow the price list provided for the budget, "
        "including any daily charges and the time each action takes to begin. Benefits are stated as **expected win**: the amount "
        "the casino would expect to retain from additional play, before the effect of luck. Each benefit is given as a most likely "
        "figure together with a low and a high estimate, because no action is certain to work as expected.\n\n"
        f"We recommend spending **{money(funded['cost'].sum())}** and retaining **{money(kept)}**. Retaining part of the budget is "
        "appropriate where no further action is expected to return more than it costs within the month.")
    kpis([tile("Recommended spending", money(funded["cost"].sum()), f"{len(funded)} actions", "payments", "purple"),
          tile("Budget retained", money(kept), "of $100,000", "savings", "teal"),
          tile("Most likely net benefit", money(pf["net_mid"].sum()), "expected win minus cost", "trending_up", "green"),
          tile("Net benefit, low estimates", money((funded["low"] - funded["cost"]).sum()), "if every action under-performs", "trending_down", "orange")])

    for r in funded.itertuples():
        s, m = sens.loc[r.action_type_id], meas.loc[r.action_type_id]
        with card(f"{r.name} · quantity {r.quantity} · cost {money(r.cost)}", WHY.get(r.action_type_id), key=f"plan_{r.action_type_id}"):
            a, b = st.columns([3, 2])
            with a:
                st.markdown(f"**Applies to:** {r.targets}")
                st.markdown(f"**Expected benefit:** {money(r.mid)} in expected win over July, within an estimated range of "
                            f"{money(r.low)} to {money(r.high)}. After its cost, the most likely net benefit is "
                            f"**{money(r.mid - r.cost, signed=True)}**.")
                st.markdown(f"**Uncertainty:** the action recovers its cost if it achieves {pct(s['break_even_share_of_mid'])} of the "
                            f"most likely benefit. At the low estimate the net result would be {money(s['net_at_low'], signed=True)}; "
                            f"if it started a week late, {money(s['net_if_lead_slips_7_days'], signed=True)}.")
            with b:
                st.markdown(f"**How the result will be measured**\n\n- *What is measured:* {m['metric']}\n- *Compared with:* "
                            f"{m['comparison']}\n- *When:* {m['check_date']}\n- *Counts as success if:* {m['success']}\n"
                            f"- *If it does not succeed:* {m['if_fails']}")
            evidence(r.claim_ids)
            if r.action_type_id in PAGE_FOR:
                page_link(*PAGE_FOR[r.action_type_id])

    with card("Range of possible results for each action", "Bar: low to high estimate of net benefit. Diamond: most likely result."):
        plot(range_chart(funded))

    section(f"Actions not recommended (budget retained: {money(kept)})")
    names = out("r1_costs").drop_duplicates("action_type_id").set_index("action_type_id")["name"]
    for r in out("r7_tradeoffs").itertuples():
        if r.action_type_id == "A-HOLD":
            continue
        label = names.get(r.action_type_id, {"RISKS": "Main risks", "KEPT": "Budget retained"}.get(r.action_type_id, r.action_type_id))
        st.markdown(f"- **{label}.** {PLAIN.get(r.action_type_id, r.reason)}")

    with detail():
        st.markdown("Every option that was priced, with its estimated benefit range and the evidence it relies on:")
        u = out("r3_benefits")[["action_type_id", "target", "unit_cost_usd", "benefit_low_usd", "benefit_mid_usd", "benefit_high_usd",
                                "net_mid_usd", "claim_ids", "how_estimated"]]
        table(u, column_config={c: st.column_config.NumberColumn(format="dollar") for c in
                                ["unit_cost_usd", "benefit_low_usd", "benefit_mid_usd", "benefit_high_usd", "net_mid_usd"]})
        st.markdown("Sensitivity of each funded action (net benefit at 50%, 100% and 150% of the most likely benefit):")
        table(sens.reset_index(), column_config={c: st.column_config.NumberColumn(format="dollar") for c in sens.columns if c.startswith("net") or c == "cost"})
        st.markdown("Best alternative combinations considered (up to three action types within $100,000):")
        table(out("r4_alternatives"), column_config={c: st.column_config.NumberColumn(format="dollar") for c in ["cost", "net_mid", "net_low"]})
        evidence("R-01")
