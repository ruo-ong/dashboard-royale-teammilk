"""Machine downtime (Q3): how much play was lost while machines were out of service, when, and why repairs took time."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import SEQUENTIAL_BLUE, date_range, evidence, money, out, pct, table, zone_bank_filter
from ui import BLUE, LIGHT_BLUE, card, detail, header, key_points, kpis, plot, section, summary, tile

ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]   # source tables use 3-letter weekdays


def render() -> None:
    s, e = date_range()
    cost = out("downtime_cost")
    cost = zone_bank_filter(cost[cost["gaming_date"].between(pd.Timestamp(s), pd.Timestamp(e))], bank_col=None)
    tickets = out("tickets_clean")
    tickets = zone_bank_filter(tickets[tickets["gaming_date"].between(pd.Timestamp(s), pd.Timestamp(e))])
    staff = out("c5_staffing")
    g = staff.groupby(["shift", "actual_headcount"]).apply(
        lambda d: pd.Series({"faults": d["faults"].sum(), "mean_response_h": (d["mean_response_h"] * d["faults"]).sum() / d["faults"].sum()}),
        include_groups=False).reset_index()
    rel = out("manufacturer_reliability")
    tech = out("tech_effect")
    best = tech[tech["estimate"] == "mid"].sort_values("benefit_30d_usd", ascending=False).iloc[0]

    header("Machine Downtime", "The play lost while machines were out of service, when it occurred, and what delayed repairs")
    kpis([tile("Expected win lost to downtime", money(cost["lost_theo_usd"].sum()), f"range {money(cost['lost_theo_low_usd'].sum())}–{money(cost['lost_theo_high_usd'].sum())}", "money_off", "red"),
          tile("Machine-hours out of service", f"{cost['down_h'].sum():,.0f}", "all causes", "timer_off", "orange"),
          tile("Caused by faults", pct(cost.loc[~cost["planned"], "down_h"].sum() / max(cost["down_h"].sum(), 1e-9)), "rather than planned work", "build", "purple"),
          tile("Fault repairs", f"{(tickets['event_type'] == 'fault_repair').sum():,}", "repair tickets", "receipt_long", "blue")])
    more_text = (
        f"For the period selected, machines were out of service for **{cost['down_h'].sum():,.0f} machine-hours**, almost all because "
        f"of faults. We value each lost hour at what that machine would normally be expected to earn at that time of day and day of "
        f"the week. On that basis, downtime cost about **{money(cost['lost_theo_usd'].sum())}** in expected win "
        f"(estimated range {money(cost['lost_theo_low_usd'].sum())} to {money(cost['lost_theo_high_usd'].sum())}). Losses are highest on "
        "Friday and Saturday evenings, when the floor is busiest.\n\n"
        "The main delay in repairs is waiting for a technician. When two technicians were on duty, work usually began almost "
        "immediately; with one technician, the average wait was between 0.7 and 2.6 hours, depending on the shift. Even so, because "
        f"total downtime costs are modest, adding a technician for July would recover only about {money(best['benefit_30d_usd'])} for a "
        f"cost of {money(11520)}, and we do not recommend it.\n\n"
        f"Machines made by {rel.iloc[0]['manufacturer']} break down {rel.iloc[0]['faults_per_1000h'] / rel.iloc[-1]['faults_per_1000h']:.1f} "
        f"times as often as those made by {rel.iloc[-1]['manufacturer']}.")
    key_points([
        f"Machines were out of service for **{cost['down_h'].sum():,.0f} machine-hours**, almost all because of faults.",
        f"Estimated cost: **{money(cost['lost_theo_usd'].sum())}** in expected win (range {money(cost['lost_theo_low_usd'].sum())} to {money(cost['lost_theo_high_usd'].sum())}).",
        "Losses are highest on **Friday and Saturday evenings**.",
        "With **two technicians on duty**, repairs start almost at once; with one, the wait averages 0.7–2.6 hours.",
        f"An extra technician would recover about {money(best['benefit_30d_usd'])} for {money(11520)}: **not recommended**.",
        f"**{rel.iloc[0]['manufacturer']}** machines break down {rel.iloc[0]['faults_per_1000h'] / rel.iloc[-1]['faults_per_1000h']:.1f} times as often as {rel.iloc[-1]['manufacturer']}."
    ], more=more_text)

    a, b = st.columns(2)
    with a:
        with card("When downtime costs the most", "Expected win lost, by day of the week and hour (darker = more), January–June"):
            h = out("c3_hour_of_week")
            grid = h.assign(wd=h["local_weekday"].str[:3]).pivot(index="wd", columns="local_hour", values="lost_theo_usd").reindex(ORDER)
            fig = go.Figure(go.Heatmap(z=grid.to_numpy(), x=[f"{x:02d}:00" for x in grid.columns], y=grid.index, colorscale=[[0, "#f0edff"], [0.5, "#8f7bff"], [1, "#2a0fbd"]],
                                       colorbar={"title": {"text": "Lost"}, "tickprefix": "$", "thickness": 10},
                                       hovertemplate="%{y} %{x}: $%{z:,.0f} lost<extra></extra>", xgap=2, ygap=2))
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, dtick=3)
            fig.update_layout(height=300)
            plot(fig)
    with b:
        with card("Expected win lost each month", "Purple: faults. Light blue: planned work (maintenance, moves, installations)."):
            m = cost.groupby(["month", "planned"])["lost_theo_usd"].sum().reset_index()
            fig = go.Figure()
            for planned, colour, name in [(False, BLUE, "Faults"), (True, LIGHT_BLUE, "Planned work")]:
                s_ = m[m["planned"] == planned]
                fig.add_trace(go.Bar(x=s_["month"], y=s_["lost_theo_usd"], name=name, marker={"color": colour},
                                     hovertemplate="%{x}: $%{y:,.0f}<extra>" + name + "</extra>"))
            fig.update_layout(barmode="stack", height=300)
            fig.update_yaxes(tickformat="$,.0f")
            plot(fig, legend_top=True)

    a, b = st.columns(2)
    with a:
        with card("Average wait for a technician", "Hours from a breakdown until a technician began work, by shift and technicians on duty"):
            g["label"] = g["shift"].str.capitalize() + " shift, " + g["actual_headcount"].astype(int).astype(str) + " on duty"
            g2 = g.sort_values(["shift", "actual_headcount"])
            fig = go.Figure(go.Bar(x=g2["mean_response_h"], y=g2["label"], orientation="h",
                                   marker={"color": [BLUE if n >= 2 else LIGHT_BLUE for n in g2["actual_headcount"]]},
                                   text=[f"{v:.1f} h ({int(n)} repairs)" for v, n in zip(g2["mean_response_h"], g2["faults"])], textposition="outside",
                                   hovertemplate="%{y}: %{x:.2f} hours<extra></extra>"))
            fig.update_xaxes(range=[0, g2["mean_response_h"].max() * 1.7], title_text="Hours")
            fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
            fig.update_layout(height=300)
            plot(fig)
    with b:
        with card("Breakdowns by manufacturer", "Faults per 1,000 hours of operation, with a 90% range"):
            r = rel.sort_values("faults_per_1000h")
            fig = go.Figure(go.Bar(x=r["faults_per_1000h"], y=r["manufacturer"], orientation="h", marker={"color": [LIGHT_BLUE, LIGHT_BLUE, BLUE]},
                                   error_x={"type": "data", "symmetric": False, "array": r["faults_per_1000h_high"] - r["faults_per_1000h"],
                                            "arrayminus": r["faults_per_1000h"] - r["faults_per_1000h_low"], "color": "#555"},
                                   text=[f"{v:.2f}" for v in r["faults_per_1000h"]], textposition="inside", insidetextanchor="start",
                                   textfont={"color": "#ffffff", "size": 13},
                                   hovertemplate="%{y}: %{x:.2f} faults per 1,000 hours<extra></extra>"))
            fig.update_yaxes(showgrid=False, automargin=True)
            fig.update_layout(height=300)
            plot(fig)

    with detail():
        st.markdown("**How each lost hour is valued.** Each hour a machine was out of service is valued at the machine's expected win "
                    "per available hour, multiplied by an index of how busy that weekday and hour usually is (0.13 overnight to 2.42 "
                    "at peak). The low and high estimates use the bank's and the machine's own rate. The figures do not deduct play that "
                    "may have moved to a neighbouring machine.")
        evidence(["C-03", "C-04", "C-01", "C-02"])
        st.markdown("Repair stages (hours), all fault tickets:")
        table(out("c5_bottleneck").query("dimension == 'all'")[["stage", "faults", "mean_h", "median_h", "p90_h"]])
        st.markdown("Waiting time by shift and technicians on duty:")
        table(staff)
        st.markdown("Chronic machines (top 5% by fault rate, or four or more repeat faults within seven days of a repair):")
        ch = zone_bank_filter(out("c7_chronic"), bank_col=None)
        table(ch[ch["chronic"]][["machine_id", "zone_name", "manufacturer", "faults", "repeat_faults", "faults_per_1000h", "unplanned_lost_theo_usd"]],
              column_config={"unplanned_lost_theo_usd": st.column_config.NumberColumn("expected win lost", format="dollar")})
        st.markdown("The ten most expensive outages:")
        table(out("c3_ticket_lost_theo").head(10)[["operation_id", "machine_id", "event_type", "opened_at_local", "shift", "zone_name", "down_h", "lost_theo_usd"]],
              column_config={"lost_theo_usd": st.column_config.NumberColumn("expected win lost", format="dollar")})
        st.markdown("Extra-technician scenario (30-day benefit by shift, low / mid / high):")
        table(tech)
