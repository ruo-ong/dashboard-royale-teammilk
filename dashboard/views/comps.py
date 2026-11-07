"""Loyalty rewards (Q5): what complimentary rewards cost, the change made on May 1, and whether it has paid for itself."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import evidence, money, out, pct, table, tracked_label
from ui import BLUE, LIGHT_BLUE, card, detail, header, kpis, plot, summary, tile


def weekly(metric: str, fmt: str, change) -> go.Figure:
    w = out("comp_weekly")
    w = w[w["full_week"]]
    fig = go.Figure(go.Bar(x=w["week"], y=w[metric], marker={"color": [LIGHT_BLUE if d < change else BLUE for d in w["week"]]},
                           hovertemplate="week of %{x|%b %d}: %{y:" + fmt + "}<extra></extra>"))
    fig.add_vline(x=change, line={"color": "#555", "width": 1, "dash": "dot"})
    fig.add_annotation(x=change, y=1, yref="paper", text=f"Change on {change:%B %-d}", showarrow=False, xanchor="left", yanchor="bottom",
                       font={"size": 11, "color": "#555"})
    fig.update_yaxes(tickformat=fmt, rangemode="tozero")
    fig.update_layout(height=300, bargap=0.2)
    return fig


def render() -> None:
    chg = out("e3_change").iloc[0]
    change = pd.Timestamp(chg["change_date"])
    imp = out("e4_change_impact")
    i0 = imp.iloc[0]
    t = imp.set_index("metric")
    s = out("e1_comp_series")
    w = out("comp_weekly")
    header("Loyalty Rewards", "The cost of complimentary food and drink, the change made on May 1, and its effect so far")
    tracked_label()
    summary(
        f"Members redeemed loyalty points for complimentary food and drink costing the casino **{money(s['comp_cost_usd'].sum())}** "
        f"between January and June (menu value {money(s['comp_face_value_usd'].sum())}). This is "
        f"{pct(w['cost_usd'].sum() / w['tracked_theo_usd'].sum(), 2)} of the expected win from member play.\n\n"
        f"On **{change:%B %-d, %Y}**, the number of points needed for each dollar of rewards was reduced from {chg['before']:.1f} to "
        f"{chg['after']:.1f}, a reduction of {pct(abs(chg['change_pct']))}. The change applied to all membership levels on the same day.\n\n"
        f"In the eight weeks after the change, rewards cost {money(i0['extra_comp_cost_per_week_usd'])} more per week than before. "
        f"Member play declined slightly, by a similar amount to the decline in Las Vegas visitors. After allowing for the city trend, "
        f"the change in member play lies somewhere between {money(i0['theo_change_net_of_city_low_usd'], signed=True)} and "
        f"{money(i0['theo_change_net_of_city_high_usd'], signed=True)} per week. Because this range includes both gains and losses, "
        "**it is not yet possible to say whether the change has paid for itself**. Since every member was affected at once, there is "
        "no comparison group; a trial in which a randomly chosen group of members keeps the earlier rate would settle the question.")
    kpis([tile("Cost of rewards, Jan–Jun", money(s["comp_cost_usd"].sum()), f"menu value {money(s['comp_face_value_usd'].sum())}", "redeem", "purple"),
          tile("Cost as a share of member play", pct(w["cost_usd"].sum() / w["tracked_theo_usd"].sum(), 2), "of expected win", "percent", "blue"),
          tile("Points needed per reward dollar", f"{chg['before']:.1f} → {chg['after']:.1f}", f"changed {change:%B %-d}, all levels", "swap_vert", "orange"),
          tile("Extra cost per week since", money(i0["extra_comp_cost_per_week_usd"]), "8 weeks after vs 8 before", "add_card", "red"),
          tile("Has it paid for itself?", "Not yet known", "no comparison group", "help", "grey")])
    a, b = st.columns(2)
    with a:
        with card("Points needed per dollar of rewards, by week", "Dark blue: after the change"):
            plot(weekly("points_per_comp_dollar", ".1f", change), key="ppd")
    with b:
        with card("Cost of rewards as a share of member play, by week", "Cost of rewards divided by the expected win from member play"):
            plot(weekly("reinvestment_rate", ".2%", change), key="reinv")
    with card("Effect of the change on each membership level", "Points needed per dollar of rewards, before and after"):
        bt = out("e3_by_tier").pivot(index="tier", columns="period", values="points_per_comp_dollar")[["before", "after"]]
        fig = go.Figure()
        for col, colour, name in [("before", LIGHT_BLUE, "Before May 1"), ("after", BLUE, "After May 1")]:
            fig.add_trace(go.Bar(x=bt.index, y=bt[col], name=name, marker={"color": colour}, text=[f"{v:.1f}" for v in bt[col]], textposition="outside"))
        fig.update_layout(barmode="group", height=280)
        plot(fig, legend_top=True)

    with detail():
        st.markdown("**Method.** The change date is the strongest break in any weekly measure of the programme. The effect is the "
                    "difference between the eight full weeks before and after, with a range of ±2 standard errors; member play is "
                    "adjusted by the change in Las Vegas visitors per day. Reward cost is already included in the cost of goods sold "
                    "and is counted once. The loyalty ledger and the point-of-sale records agree to the cent.")
        evidence(["E-01", "E-02"])
        table(imp[["metric", "mean_before", "mean_after", "change_pct", "change_low", "change_high"]],
              column_config={"change_pct": st.column_config.NumberColumn("change", format="percent")}
              | {c: st.column_config.NumberColumn(format="localized") for c in ["mean_before", "mean_after", "change_low", "change_high"]})
        table(out("e3_breaks"))
        st.markdown("Reward economics by membership level (level at the end of the period):")
        table(out("e5_tier_economics"))
