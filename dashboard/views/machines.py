"""W3 - Q1, the machine trial: manager's list -> tests -> decomposition -> verdicts -> any machine -> floor map.

Recomputes live for the sidebar's date range (judge task 1) with the task scripts' own compute() functions.
The manager's list itself is fixed (the GM ranked January-June).
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, chart, date_range, evidence, filter_note, is_full_window, money, out, pct, style, table, zone_bank_filter
from royale.data import load_base
from tasks import a2_exposure, a3_luck, a4_leak, a5_location, a8_decomposition, a9_verdicts
from tasks.a1_manager_list import manager_ten


@st.cache_data(show_spinner="Re-running the machine trial for this period (about 15 seconds)...")
def trial(start, end) -> dict:
    if (start, end) == (pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-06-30").date()):
        return {"exposure": out("a2_exposure"), "luck": out("a3_luck"), "leak": out("a4_leak"), "tickets": out("a4_ticket_changes"),
                "location": out("a5_location"), "banks": out("bank_scores"), "verdicts": out("machine_verdicts"),
                "dec": None, "base": load_base(start, end)}
    base = load_base(start, end)
    ids = manager_ten()
    exposure = a2_exposure.compute(base, start, end, ids)
    luck, _ = a3_luck.compute(base, ids)
    leak, tickets = a4_leak.compute(base, ids)
    location, banks, _ = a5_location.compute(base, ids)
    dec = a8_decomposition.compute(base, start, end, ids, location)
    zones = set(out("closure_effect")["affected_zones"].iloc[0].split(", "))
    verdicts = a9_verdicts.compute(base, start, end, out("c7_chronic"), zones, ids, exposure, leak, location, dec)
    return {"exposure": exposure, "luck": luck, "leak": leak, "tickets": tickets, "location": location, "banks": banks,
            "verdicts": verdicts, "dec": dec, "base": base}


def funnel(verdicts: pd.DataFrame) -> go.Figure:
    ten = verdicts[verdicts["in_manager_10"]]
    missing = [m for m in manager_ten() if m not in set(ten["machine_id"])]
    steps = [("On the manager's list", 10, ""),
             ("On the floor in this period, with ≥ 60 days of data", len(ten) - (ten["verdict"] == "Watch list").sum(),
              ", ".join(list(ten.loc[ten["verdict"] == "Watch list", "machine_id"]) + [f"{m} (not on the floor)" for m in missing])),
             ("Not an inspection lead (payout looks right)", None, ", ".join(ten.loc[ten["verdict"] == "Inspect", "machine_id"])),
             ("Not explained by location, luck, short stay or game setting", None, "")]
    n2 = steps[1][1] - (ten["verdict"] == "Inspect").sum()
    n3 = int((ten["verdict"] == "Truly weak").sum())
    steps[2] = (steps[2][0], n2, steps[2][2])
    explained = ten[~ten["verdict"].isin(["Watch list", "Inspect", "Truly weak"])]
    steps[3] = (steps[3][0], n3, ", ".join(f"{m} ({v})" for m, v in zip(explained["machine_id"], explained["verdict"])))
    steps = [steps[0]] + steps[1:]
    labels = [s[0] for s in steps][::-1]
    values = [s[1] for s in steps][::-1]
    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", text=[str(v) for v in values], textposition="outside",
                           marker={"color": [COLORS["series_2"]] + [COLORS["series_1"]] * 3},
                           customdata=[s[2] for s in steps][::-1],
                           hovertemplate="%{y}: %{x}<br>dropped here: %{customdata}<extra></extra>"))
    style(fig, f"{n3} of the manager's 10 survive every test", "Machines left after each test (hover to see who dropped and why)", height=300)
    fig.update_xaxes(range=[0, 11.5], title_text="Machines", dtick=2)
    fig.update_yaxes(showgrid=False)
    return fig


def cumulative(base: pd.DataFrame, machine_id: str) -> go.Figure:
    d = base[base["machine_id"] == machine_id].sort_values("gaming_date")
    cum, band, x = d["luck_residual_usd"].cumsum(), 2 * np.sqrt(d["luck_var_usd2"].cumsum()), d["gaming_date"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.concat([x, x[::-1]]), y=pd.concat([band, -band[::-1]]), fill="toself", fillcolor=COLORS["grid"],
                             line={"width": 0}, hoverinfo="skip", name="Ordinary luck (±2 SD)"))
    fig.add_trace(go.Scatter(x=x, y=cum, mode="lines", line={"color": COLORS["series_1"], "width": 2}, name="House win − theo, running",
                             hovertemplate="%{x|%b %d}: %{y:$,.0f}<extra></extra>"))
    outside = abs(cum.iloc[-1]) > band.iloc[-1]
    style(fig, f"{machine_id}: luck {'is outside' if outside else 'stays inside'} the band chance explains",
          "Running total of house win − theo; grey = ±2 standard deviations of luck for the play so far", height=340)
    fig.update_yaxes(tickformat="$,.0f")
    fig.update_layout(legend={"y": -0.25, "x": 0, "xanchor": "left"})
    return fig


def machine_pieces(v: pd.Series) -> go.Figure:
    pieces = [(c, label, col) for c, label, col in a8_decomposition.PIECES]
    fig = go.Figure(go.Bar(x=[v[c] for c, _, _ in pieces], y=[label for _, label, _ in pieces], orientation="h",
                           marker={"color": [col for _, _, col in pieces]},
                           hovertemplate="%{y}: %{x:$,.0f}<extra></extra>"))
    fig.add_vline(x=0, line={"color": COLORS["text_secondary"], "width": 1})
    style(fig, f"Gap vs a typical machine: {money(v['gap_usd'], signed=True)}", "Each piece in dollars; they add up to the gap", height=300)
    fig.update_xaxes(tickformat="$,.0f")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def render() -> None:
    start, end = date_range()
    st.title("Q1 · The machine trial: luck, location, or a leak?")
    filter_note()
    if not is_full_window():
        st.caption("Tests recomputed for this period. The manager's list stays the January–June bottom 10 by house win.")
    t = trial(start, end)
    v = t["verdicts"]
    ids = manager_ten()

    chart(funnel(v))
    evidence(["A1-01", "A9-01"])

    st.subheader("Why each machine earned less than a typical one")
    dec = t["dec"] if t["dec"] is not None else a8_decomposition.compute(t["base"], start, end, ids, t["location"])
    chart(a8_decomposition.figure(dec, ids))
    evidence("A8-01")

    st.subheader("Verdicts")
    cols = ["machine_id", "zone_name", "bank_id", "theme", "verdict", "reason", "advice"]
    tab1, tab2, tab3 = st.tabs(["The manager's 10", "Our replacement list", "Every machine (zone / bank filters apply)"])
    with tab1:
        table(v[v["in_manager_10"]][cols])
    with tab2:
        table(v[v["on_our_list"]].sort_values("replace_rank")[cols])
        evidence("A5-03")
    with tab3:
        allv = zone_bank_filter(v)
        st.caption(", ".join(f"{k}: {n}" for k, n in allv["verdict"].value_counts().items()))
        table(allv[cols + ["gap_usd", "peer_index", "volume_peer_index", "luck_z"]],
              column_config={"gap_usd": st.column_config.NumberColumn("gap vs typical", format="dollar")})

    st.subheader("Look at any machine")
    present = set(v["machine_id"])
    order = [m for m in ids if m in present] + [m for m in v["machine_id"] if m not in ids]
    pick = st.selectbox("Machine", order, index=0, help="The manager's 10 first, then every other machine")
    r = v.set_index("machine_id").loc[pick]
    st.markdown(f"**{pick}** · {r['zone_name']} · {r['bank_id']} · {r['theme']} → **{r['verdict']}**. {r['reason']} *{r['advice']}*")
    k = st.columns(5)
    kpi(k[0], "Theo per available hour", money(r["tpah"], 2))
    kpi(k[1], "vs bank peers (theo)", f"{r['peer_index']:.2f}×")
    kpi(k[2], "vs bank peers (play volume)", f"{r['volume_peer_index']:.2f}×")
    kpi(k[3], "Luck z", f"{round(r['luck_z'], 1) + 0.0:+.1f}")
    kpi(k[4], "Hit-rate z", f"{round(r['hit_rate_z'], 1) + 0.0:+.1f}")
    a, b = st.columns(2)
    with a:
        chart(machine_pieces(r), key="pieces")
    with b:
        chart(cumulative(t["base"], pick), key="cum")

    st.subheader("The four tests")
    e, l, k_, loc = st.tabs(["Exposure (A2)", "Luck (A3)", "Leak (A4)", "Location (A5)"])
    with e:
        chart(a2_exposure.rank_shift_figure(t["exposure"]))
        evidence("A2-01")
    with l:
        chart(a3_luck.histogram_figure(t["luck"]))
        evidence("A3-01")
    with k_:
        fig = a4_leak.cumulative_figure(t["base"], t["leak"], t["tickets"])
        if fig is not None:
            chart(fig)
        leads = t["leak"][t["leak"]["inspection_lead"]]
        st.markdown(f"**{len(leads)} inspection lead(s)** in this period. Wording rule: a lead is a reason to inspect, not proof of wrongdoing.")
        table(leads[["machine_id", "reason"]])
        evidence(["A4-01", "A4-02"])
    with loc:
        banks = t["banks"]
        chart(a5_location.floor_map_figure(banks))
        b2 = zone_bank_filter(banks)
        table(b2[["bank_id", "zone_name", "machines", "tpah", "occupancy", "bank_rank", "bank_quartile", "manager_10_machines"]],
              column_config={"tpah": st.column_config.NumberColumn("TPAH", format="dollar"),
                             "occupancy": st.column_config.NumberColumn(format="percent")})
        evidence(["A5-01", "A5-02", "A6-01"])
