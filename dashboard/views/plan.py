"""Recommended actions: each funded action at a glance, with measurement, certainty and evidence one click away."""
import plotly.graph_objects as go
import streamlit as st

from common import evidence, money, out, page_link, pct, table
from ui import BLUE, card, chips, detail, header, key_points, kpis, plot, section, tile

SHORT = {"A-INSPECT": "Inspect machine M-1158", "A-MOVE-MACHINE": "Move three Back Forty machines",
         "A-PROMO": "Hold two promotion weekends"}
WHY = {"A-INSPECT": "Its payouts do not match its published settings, in every month reviewed.",
       "A-MOVE-MACHINE": "The Back Forty is the quietest area; three empty positions exist in busier areas.",
       "A-PROMO": "Our own promotion weekends have raised play by 6% to 18%."}
PAGE_FOR = {"A-PROMO": ("demand", "Evidence: visitor demand"), "A-INSPECT": ("machines", "Evidence: machine review"),
            "A-MOVE-MACHINE": ("machines", "Evidence: machine review")}
NOT_FUNDED = {"A-TECH-SHIFT": "Extra technician: would recover about $500 of expected win for an $11,520 cost.",
              "A-REPLACE-LEASE": "Leased replacements: run only 16 of the 30 days; each loses $1,458 or more.",
              "A-REPLACE-BUY": "Purchased replacements: $22,000 each for 9 days of operation.",
              "A-PREVENTIVE": "Preventive maintenance: only three past maintenance visits, too few to show a benefit.",
              "A-WAYFINDING": "New signs for the Back Forty: expected $5,181 against a $7,500 cost.",
              "A-COMP-PILOT": "Rewards trial: answers a question but adds no win in July.",
              "A-MOVE-BANK": "Moving a whole bank: no empty space large enough.",
              "A-COMP-CHANGE": "Changing the rewards rate again: no evidence the May change helped or hurt.",
              "A-SURVEY": "Larger guest survey: no decision here depends on it."}


def range_chart(funded) -> go.Figure:
    f = funded.sort_values("mid")
    names = [SHORT.get(a, n) for a, n in zip(f["action_type_id"], f["name"])]
    fig = go.Figure()
    for (r, name) in zip(f.itertuples(), names):
        fig.add_trace(go.Scatter(x=[r.low - r.cost, r.high - r.cost], y=[name] * 2, mode="lines",
                                 line={"color": "#c9bfff", "width": 14}, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f["mid"] - f["cost"], y=names, mode="markers", marker={"size": 13, "color": BLUE, "symbol": "diamond"},
                             hovertemplate="%{y}<br>most likely net benefit %{x:$,.0f}<extra></extra>", showlegend=False))
    fig.add_trace(go.Scatter(x=f["high"] - f["cost"], y=names, mode="text", text=["  most likely " + money(v, signed=True) for v in f["mid"] - f["cost"]],
                             textposition="middle right", textfont={"color": "#2b3674", "size": 13}, hoverinfo="skip", showlegend=False))
    fig.update_xaxes(range=[min(0, (f["low"] - f["cost"]).min()) * 1.1 - 2000, (f["high"] - f["cost"]).max() * 1.35])
    fig.add_vline(x=0, line={"color": "#a3aed0", "width": 1})
    fig.update_xaxes(tickformat="$,.0f", title_text="Net benefit in July (expected win minus cost)")
    fig.update_layout(height=270)
    return fig


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"].reset_index(drop=True)
    sens = out("r5_sensitivity").set_index("action_type_id")
    meas = out("r6_measurement").set_index("action_type_id")
    lead = out("r1_costs").drop_duplicates("action_type_id").set_index("action_type_id")["lead_days"]
    kept = pf["kept_usd"].dropna().iloc[0]

    header("Recommended Actions", "How we propose to use the $100,000 budget", chip="Jul 1 – Jul 30, 2025")
    kpis([tile("Recommended spending", money(funded["cost"].sum()), f"{len(funded)} actions", "payments", "indigo"),
          tile("Budget retained", money(kept), "of $100,000", "savings", "teal"),
          tile("Most likely net benefit", money(pf["net_mid"].sum()), "expected win minus cost", "trending_up", "green"),
          tile("If every action under-performs", money((funded["low"] - funded["cost"]).sum()), "net, low estimates", "trending_down", "orange")])
    key_points([f"**Three actions** for **{money(funded['cost'].sum())}**; **{money(kept)}** is retained.",
                "Each action addresses a cause identified in the review.",
                "Benefits are **expected win**: what the casino expects to keep from extra play, before luck.",
                "Every benefit has a low and a high estimate; no action is certain to work."],
               more="Costs follow the price list supplied for the budget, including daily charges and the time each action takes to "
                    "begin. Benefits count only the days remaining in July after that lead time, less any downtime the action "
                    "itself causes. Retaining part of the budget is appropriate where no further action is expected to return more "
                    "than it costs within the month.")

    section("The three actions")
    for i, r in enumerate(funded.itertuples(), start=1):
        s, m = sens.loc[r.action_type_id], meas.loc[r.action_type_id]
        with card(f"{i}. {SHORT.get(r.action_type_id, r.name)}", WHY.get(r.action_type_id), key=f"plan_{r.action_type_id}"):
            chips([("Cost", money(r.cost)), ("Most likely benefit", money(r.mid)),
                   ("Range", f"{money(r.low)} to {money(r.high)}"), ("Net benefit", money(r.mid - r.cost, signed=True))])
            targets = [t.strip() for t in str(r.targets).split(";")]
            st.markdown(f"- **Applies to:** " + ("; ".join(targets) if len(targets) == 1 else "\n" + "\n".join(f"    - {t}" for t in targets)))
            st.markdown(f"- **Takes effect:** {int(lead[r.action_type_id])} day(s) after ordering")
            a, b, c = st.columns(3)
            with a:
                with st.expander("How we will measure it"):
                    st.markdown(f"- **Measure:** {m['metric']}\n- **Compare with:** {m['comparison']}\n- **When:** {m['check_date']}\n"
                                f"- **Success if:** {m['success']}\n- **If not:** {m['if_fails']}")
            with b:
                with st.expander("How certain is it?"):
                    st.markdown(f"- Pays for itself at **{pct(s['break_even_share_of_mid'])}** of the most likely benefit\n"
                                f"- At the low estimate: **{money(s['net_at_low'], signed=True)}**\n"
                                f"- If it starts a week late: **{money(s['net_if_lead_slips_7_days'], signed=True)}**")
            with c:
                evidence(r.claim_ids, "Supporting evidence")
            if r.action_type_id in PAGE_FOR:
                page_link(*PAGE_FOR[r.action_type_id])

    with card("Range of possible results", "Bar: low to high estimate of net benefit. Diamond: most likely result."):
        plot(range_chart(funded))

    section("Not recommended")
    with card(f"Why {money(kept)} is retained", "Each option below is expected to cost more than it returns within July"):
        ids = [a for a in out("r7_tradeoffs")["action_type_id"] if a in NOT_FUNDED]
        st.markdown("\n".join(f"- {NOT_FUNDED[a]}" for a in ids))
        risks = out("r7_tradeoffs").set_index("action_type_id")
        if "RISKS" in risks.index:
            with st.expander("Main risks to the plan"):
                st.markdown("\n".join(f"- {x.strip()}" for x in risks.loc["RISKS", "reason"].split(";")))

    with detail():
        st.markdown("Every option that was priced, with its estimated benefit range and the evidence it relies on:")
        u = out("r3_benefits")[["action_type_id", "target", "unit_cost_usd", "benefit_low_usd", "benefit_mid_usd", "benefit_high_usd",
                                "net_mid_usd", "claim_ids", "how_estimated"]]
        table(u, column_config={c: st.column_config.NumberColumn(format="dollar") for c in
                                ["unit_cost_usd", "benefit_low_usd", "benefit_mid_usd", "benefit_high_usd", "net_mid_usd"]})
        st.markdown("Sensitivity of each funded action:")
        table(sens.reset_index(), column_config={c: st.column_config.NumberColumn(format="dollar") for c in sens.columns if c.startswith("net") or c == "cost"})
        st.markdown("Best alternative combinations considered (up to three action types within $100,000):")
        table(out("r4_alternatives"), column_config={c: st.column_config.NumberColumn(format="dollar") for c in ["cost", "net_mid", "net_low"]})
        evidence("R-01")
