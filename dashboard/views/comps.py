"""W7 - Q5, comps: what the program cost, what changed, and whether it worked."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, chart, evidence, money, out, pct, style, table, tracked_label


def weekly(metric: str, title: str, subtitle: str, fmt: str, change) -> go.Figure:
    w = out("comp_weekly")
    w = w[w["full_week"]]
    fig = go.Figure(go.Scatter(x=w["week"], y=w[metric], mode="lines+markers", line={"color": COLORS["series_1"], "width": 2},
                               marker={"size": 6}, hovertemplate="week of %{x|%b %d}: %{y:" + fmt + "}<extra></extra>", showlegend=False))
    fig.add_vline(x=change, line={"color": COLORS["text_secondary"], "width": 1, "dash": "dot"})
    fig.add_annotation(x=change, y=1, yref="paper", text=f"change {change:%b %-d}", showarrow=False, xanchor="left",
                       yanchor="bottom", font={"size": 12, "color": COLORS["text_secondary"]})
    style(fig, title, subtitle, height=320)
    fig.update_yaxes(tickformat=fmt, rangemode="tozero")
    return fig


def render() -> None:
    st.title("Q5 · The comp program: cost, change, and impact")
    tracked_label()
    chg = out("e3_change").iloc[0]
    change = pd.Timestamp(chg["change_date"])
    imp = out("e4_change_impact")
    i0 = imp.iloc[0]
    s = out("e1_comp_series")
    w = out("comp_weekly")
    k = st.columns(4)
    kpi(k[0], "Comp cost, Jan–Jun", money(s["comp_cost_usd"].sum()), f"face value {money(s['comp_face_value_usd'].sum())}")
    kpi(k[1], "Reinvestment rate", pct(w["cost_usd"].sum() / w["tracked_theo_usd"].sum(), 2), "comp cost ÷ tracked theo")
    kpi(k[2], "Points per comp dollar", pct(chg["change_pct"], 0, True), f"changed on {change:%b %-d}, every tier at once")
    kpi(k[3], "Did it pay for itself?", i0["verdict"].capitalize())
    st.caption("Comp cost is already inside POS cost of goods: it is subtracted once, never twice. Ledger and POS reconcile to the cent.")

    a, b = st.columns(2)
    with a:
        chart(weekly("points_per_comp_dollar", f"On {change:%b %-d} comps got {pct(abs(chg['change_pct']))} cheaper in points",
                     "Loyalty points redeemed per dollar of comp face value, by week", ".1f", change), key="ppd")
    with b:
        chart(weekly("reinvestment_rate", "Yet comp spending barely moved",
                     "Comp cost ÷ tracked theo, by week", ".2%", change), key="reinv")
    evidence("E-01")

    st.subheader("Did the change work?")
    t = imp.set_index("metric")
    st.markdown(
        f"In the {int(t.loc['cost_usd', 'weeks_after'])} weeks after vs the {int(t.loc['cost_usd', 'weeks_before'])} weeks before: "
        f"redemptions {pct(t.loc['redemptions', 'change_pct'], 1, True)}, comp cost {pct(t.loc['cost_usd', 'change_pct'], 1, True)} "
        f"({money(i0['extra_comp_cost_per_week_usd'], signed=True)}/week), active carded players {pct(t.loc['active_players', 'change_pct'], 1, True)}, "
        f"tracked theo {pct(t.loc['tracked_theo_usd', 'change_pct'], 1, True)} while Las Vegas visitors moved {pct(i0['city_visitors_change_pct'], 1, True)}. "
        f"Net of the city trend, tracked theo changed **{money(i0['theo_change_net_of_city_per_week_usd'], signed=True)}/week** "
        f"(range {money(i0['theo_change_net_of_city_low_usd'], signed=True)} to {money(i0['theo_change_net_of_city_high_usd'], signed=True)}). "
        f"**Verdict: {i0['verdict']}.** Every tier changed on the same day, so there is no untreated group to compare with; "
        "a pilot with a randomly assigned control group is how to get a clean answer.")
    table(imp[["metric", "mean_before", "mean_after", "change_pct", "change_low", "change_high"]],
          column_config={"change_pct": st.column_config.NumberColumn("change", format="percent")}
          | {c: st.column_config.NumberColumn(format="localized") for c in ["mean_before", "mean_after", "change_low", "change_high"]})
    evidence("E-02")

    a, b = st.columns(2)
    with a:
        st.markdown("**Points per comp dollar by tier, before vs after**")
        bt = out("e3_by_tier").pivot(index="tier", columns="period", values="points_per_comp_dollar")[["before", "after"]]
        table(bt.reset_index(), column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ["before", "after"]})
    with b:
        st.markdown("**Comp economics by tier (tier at the end of the period)**")
        te = out("e5_tier_economics")
        table(te[["tier", "players", "theo_per_player_usd", "comp_cost_per_player_usd", "contribution_per_player_usd", "reinvestment_rate"]],
              column_config={c: st.column_config.NumberColumn(format="dollar") for c in ["theo_per_player_usd", "comp_cost_per_player_usd", "contribution_per_player_usd"]}
              | {"reinvestment_rate": st.column_config.NumberColumn(format="percent")})
