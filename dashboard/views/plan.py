"""W9 - The $100k plan: one card per funded action, each traceable to its evidence (judge task 4)."""
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, chart, evidence, money, out, page_link, pct, style, table

PAGE_FOR = {"A-PROMO": ("demand", "Demand page: event and promotion uplift"),
            "A-INSPECT": ("machines", "Machine trial: the leak test"),
            "A-MOVE-MACHINE": ("machines", "Machine trial: location test and floor map"),
            "A-REPLACE-LEASE": ("machines", "Machine trial: verdicts"),
            "A-COMP-PILOT": ("comps", "Comps page")}


def tornado(sens) -> go.Figure:
    s = sens.sort_values("net_at_100pct")
    fig = go.Figure()
    for r in s.itertuples():
        fig.add_trace(go.Scatter(x=[r.net_at_low, r.net_at_high], y=[r.name] * 2, mode="lines",
                                 line={"color": COLORS["series_1"], "width": 10}, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=s["net_at_100pct"], y=s["name"], mode="markers", name="Mid estimate",
                             marker={"symbol": "diamond", "size": 12, "color": COLORS["text"]},
                             hovertemplate="%{y}<br>net at mid %{x:$,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=s["net_if_lead_slips_7_days"], y=s["name"], mode="markers", name="If the lead time slips 7 days",
                             marker={"symbol": "line-ns-open", "size": 16, "color": COLORS["series_2"], "line": {"width": 3}},
                             hovertemplate="%{y}<br>net if 7 days late %{x:$,.0f}<extra></extra>"))
    fig.add_vline(x=0, line={"color": COLORS["text_secondary"], "width": 1})
    style(fig, "The promotion carries the plan; every action is worth doing at its mid estimate",
          "Net 30-day theo (benefit − cost) for each funded action: bar = low to high estimate, ◆ = mid", height=320)
    fig.update_xaxes(tickformat="$,.0f", title_text="Net theo over July 1–30")
    fig.update_layout(legend={"y": -0.35, "x": 0, "xanchor": "left"})
    return fig


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"]
    sens = out("r5_sensitivity").set_index("action_type_id")
    meas = out("r6_measurement").set_index("action_type_id")
    kept = pf["kept_usd"].dropna().iloc[0]

    st.title("The $100,000 plan for July 1–30")
    st.markdown("Up to three action types from the catalogue, each matched to a cause we found, priced with the guide's "
                "formula (unit cost + daily cost × days after the lead time). Benefits are **theo** (expected house win) for "
                "the days left after each action's lead time, minus its own downtime.")
    c = st.columns(4)
    kpi(c[0], "Spent", money(funded["cost"].sum()))
    kpi(c[1], "Kept", money(kept))
    kpi(c[2], "Expected net theo (mid)", money(pf["net_mid"].sum()))
    kpi(c[3], "At the low estimates", money((funded["low"] - funded["cost"]).sum()))

    for r in funded.itertuples():
        s, m = sens.loc[r.action_type_id], meas.loc[r.action_type_id]
        with st.container(border=True):
            st.subheader(f"{r.name} ×{r.quantity}  ·  {money(r.cost)}")
            a, b = st.columns([3, 2])
            with a:
                st.markdown(f"**Targets:** {r.targets}")
                st.markdown(f"**Expected effect:** {money(r.mid)} of theo over July (range **{money(r.low)} to {money(r.high)}**), "
                            f"net **{money(r.mid - r.cost, signed=True)}**.")
                st.markdown(f"**Uncertainty:** breaks even at {pct(s['break_even_share_of_mid'])} of the mid benefit; "
                            f"net at the low estimate {money(s['net_at_low'], signed=True)}; "
                            f"if the lead time slips 7 days {money(s['net_if_lead_slips_7_days'], signed=True)}.")
            with b:
                st.markdown(f"**How we'll know it worked**\n- **Metric:** {m['metric']}\n- **Compared with:** {m['comparison']}\n"
                            f"- **Check:** {m['check_date']}\n- **Success:** {m['success']}\n- **If it fails:** {m['if_fails']}")
            evidence(r.claim_ids, "Evidence behind this action")
            if r.action_type_id in PAGE_FOR:
                page_link(*PAGE_FOR[r.action_type_id])

    st.subheader(f"Kept: {money(kept)}")
    st.markdown("Keeping money is a valid answer. Nothing else in the catalogue is expected to return its cost within 30 days:")
    names = out("r1_costs").drop_duplicates("action_type_id").set_index("action_type_id")["name"]
    for r in out("r7_tradeoffs").itertuples():
        label = names.get(r.action_type_id, r.action_type_id.capitalize())
        st.markdown(f"- **{label}**: {r.reason}")

    chart(tornado(sens.reset_index()))
    with st.expander("Every option we priced (r3_benefits)"):
        u = out("r3_benefits")[["action_type_id", "target", "unit_cost_usd", "benefit_low_usd", "benefit_mid_usd",
                                "benefit_high_usd", "net_mid_usd", "claim_ids", "how_estimated"]]
        table(u, column_config={c: st.column_config.NumberColumn(format="dollar") for c in
                                ["unit_cost_usd", "benefit_low_usd", "benefit_mid_usd", "benefit_high_usd", "net_mid_usd"]})
    with st.expander("Best alternative portfolios (r4_alternatives)"):
        table(out("r4_alternatives"), column_config={c: st.column_config.NumberColumn(format="dollar") for c in ["cost", "net_mid", "net_low"]})
    evidence("R-01", "The recommendation")
