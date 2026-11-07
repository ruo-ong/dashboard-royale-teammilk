"""W5 - Q3, downtime: how much play was lost, when, and what the bottleneck was."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, SEQUENTIAL_BLUE, chart, date_range, evidence, filter_note, money, out, pct, style, table, zone_bank_filter

ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]   # source tables use 3-letter weekdays


def render() -> None:
    st.title("Q3 · Downtime: how much play was lost, and when")
    filter_note()
    s, e = date_range()
    cost = out("downtime_cost")
    cost = zone_bank_filter(cost[cost["gaming_date"].between(pd.Timestamp(s), pd.Timestamp(e))], bank_col=None)
    tickets = out("tickets_clean")
    tickets = zone_bank_filter(tickets[tickets["gaming_date"].between(pd.Timestamp(s), pd.Timestamp(e))])

    k = st.columns(4)
    kpi(k[0], "Theo lost to downtime", money(cost["lost_theo_usd"].sum()),
                f"range {money(cost['lost_theo_low_usd'].sum())}–{money(cost['lost_theo_high_usd'].sum())}")
    kpi(k[1], "Machine-hours down", f"{cost['down_h'].sum():,.0f}")
    kpi(k[2], "Unplanned (faults)", pct(cost.loc[~cost["planned"], "down_h"].sum() / max(cost["down_h"].sum(), 1e-9)))
    kpi(k[3], "Fault tickets", f"{(tickets['event_type'] == 'fault_repair').sum():,}")
    st.caption("Each down hour is valued at the machine's theo per available hour × how busy that weekday-hour usually is. "
               "It is expected play, not house win, and gross of play that may have moved to a neighbouring machine.")
    evidence(["C-03", "C-04"])

    a, b = st.columns(2)
    with a:
        h = out("c3_hour_of_week")
        grid = h.assign(wd=h["local_weekday"].str[:3]).pivot(index="wd", columns="local_hour", values="lost_theo_usd").reindex(ORDER)
        fig = go.Figure(go.Heatmap(z=grid.to_numpy(), x=[f"{x:02d}:00" for x in grid.columns], y=grid.index, colorscale=SEQUENTIAL_BLUE,
                                   colorbar={"title": {"text": "theo lost"}, "tickprefix": "$", "thickness": 10},
                                   hovertemplate="%{y} %{x}: $%{z:,.0f} theo lost<extra></extra>", xgap=2, ygap=2))
        top = h.loc[h["lost_theo_usd"].idxmax()]
        style(fig, f"Evenings cost the most; worst slot {top['local_weekday']} {int(top['local_hour']):02d}:00",
              "Theo lost by weekday × local hour, January–June (darker = more)", height=380)
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=False, dtick=3)
        chart(fig)
    with b:
        m = cost.groupby(["month", "planned"])["lost_theo_usd"].sum().reset_index()
        fig = go.Figure()
        for planned, colour, name in [(False, COLORS["series_1"], "Unplanned (faults)"), (True, COLORS["series_2"], "Planned (maintenance, moves, installs)")]:
            s_ = m[m["planned"] == planned]
            fig.add_trace(go.Bar(x=s_["month"], y=s_["lost_theo_usd"], name=name, marker={"color": colour, "line": {"color": COLORS["surface"], "width": 2}},
                                 hovertemplate="%{x}: $%{y:,.0f}<extra>" + name + "</extra>"))
        style(fig, "Monthly downtime cost is flat: no month stands out", "Theo lost per month", height=380)
        fig.update_layout(barmode="stack", legend={"y": -0.3, "x": 0, "xanchor": "left"})
        fig.update_yaxes(tickformat="$,.0f")
        chart(fig)

    st.subheader("The bottleneck: waiting for a technician")
    stg = out("c5_bottleneck")
    allf = stg[stg["dimension"] == "all"]
    staff = out("c5_staffing")
    g = staff.groupby(["shift", "actual_headcount"]).apply(
        lambda d: pd.Series({"faults": d["faults"].sum(), "mean_response_h": (d["mean_response_h"] * d["faults"]).sum() / d["faults"].sum()}),
        include_groups=False).reset_index()
    g["label"] = g["shift"].str.capitalize() + " shift · " + g["actual_headcount"].astype(int).astype(str) + " tech(s) on duty"
    g = g.sort_values(["shift", "actual_headcount"])
    a, b = st.columns(2)
    with a:
        fig = go.Figure(go.Bar(x=g["mean_response_h"], y=g["label"], orientation="h", marker={"color": COLORS["series_1"]},
                               text=[f"{v:.1f} h ({int(n)} faults)" for v, n in zip(g["mean_response_h"], g["faults"])], textposition="outside",
                               hovertemplate="%{y}: %{x:.2f} h average wait<extra></extra>"))
        style(fig, "With 2 technicians on duty, repairs start almost at once", "Average hours from breakdown to a technician starting work", height=380)
        fig.update_xaxes(range=[0, g["mean_response_h"].max() * 1.9], title_text="Hours")
        fig.update_yaxes(autorange="reversed", showgrid=False)
        chart(fig)
    with b:
        fig = go.Figure()
        for col, name, colour in [("median_h", "Median", COLORS["series_1"]), ("p90_h", "90th percentile", COLORS["series_2"])]:
            fig.add_trace(go.Bar(x=allf[col], y=allf["stage"], orientation="h", name=name, marker={"color": colour},
                                 hovertemplate="%{y}: %{x:.2f} h<extra>" + name + "</extra>"))
        style(fig, "The repair itself takes ~2.5 h; the wait is what varies", "Hours per repair stage, all fault tickets", height=380)
        fig.update_layout(barmode="group", legend={"y": -0.2, "x": 0, "xanchor": "left"})
        fig.update_yaxes(autorange="reversed", showgrid=False)
        chart(fig)
    tech = out("tech_effect")
    mid = tech[tech["estimate"] == "mid"].sort_values("benefit_30d_usd", ascending=False).iloc[0]
    st.markdown(f"**But an extra technician does not pay for itself:** the best case is the {mid['shift']} shift, saving about "
                f"{money(mid['benefit_30d_usd'])} of theo over July for an {money(11520)} cost, because downtime is cheap overall.")
    evidence("C-01")

    st.subheader("Reliability by manufacturer and the machines that keep breaking")
    a, b = st.columns(2)
    with a:
        r = out("manufacturer_reliability").sort_values("faults_per_1000h")
        fig = go.Figure(go.Scatter(x=r["faults_per_1000h"], y=r["manufacturer"], mode="markers",
                                   marker={"size": 12, "color": COLORS["series_1"]},
                                   error_x={"type": "data", "symmetric": False, "array": r["faults_per_1000h_high"] - r["faults_per_1000h"],
                                            "arrayminus": r["faults_per_1000h"] - r["faults_per_1000h_low"], "thickness": 2, "width": 0},
                                   customdata=r[["faults", "machines", "mean_total_h"]].to_numpy(),
                                   hovertemplate="%{y}: %{x:.2f} faults per 1,000 h<br>%{customdata[0]} faults, %{customdata[1]} machines, "
                                                 "%{customdata[2]:.1f} h out per fault<extra></extra>"))
        worst = r.iloc[-1]
        style(fig, f"{worst['manufacturer']} machines break {worst['faults_per_1000h'] / r.iloc[0]['faults_per_1000h']:.1f}× as often as {r.iloc[0]['manufacturer']}",
              "Faults per 1,000 available hours, with 90% intervals", height=300)
        fig.update_xaxes(rangemode="tozero")
        fig.update_yaxes(showgrid=False)
        chart(fig)
        evidence("C-02")
    with b:
        ch = zone_bank_filter(out("c7_chronic"), bank_col=None)
        st.markdown(f"**{int(ch['chronic'].sum())} chronic machines** (top 5% by fault rate, or 4+ repeat faults within 7 days of a repair)")
        table(ch[ch["chronic"]][["machine_id", "zone_name", "manufacturer", "faults", "repeat_faults", "faults_per_1000h", "unplanned_lost_theo_usd"]],
              column_config={"unplanned_lost_theo_usd": st.column_config.NumberColumn("theo lost", format="dollar"),
                             "faults_per_1000h": st.column_config.NumberColumn(format="%.2f")}, height=300)
    with st.expander("The 10 most expensive outages"):
        top = out("c3_ticket_lost_theo").head(10)
        table(top[["operation_id", "machine_id", "event_type", "opened_at_local", "shift", "zone_name", "down_h", "lost_theo_usd", "response_h", "repair_h"]],
              column_config={"lost_theo_usd": st.column_config.NumberColumn("theo lost", format="dollar")})
