"""Machine review (Q1): is each machine on the proposed list weak, or are other circumstances responsible?

Recomputes for the sidebar's period with the task scripts' own compute() functions.
The proposed list itself is fixed (management ranked January-June).
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import PLAIN_ADVICE, PLAIN_VERDICT, date_range, evidence, is_full_window, money, out, table, zone_bank_filter
from royale.data import load_base
from tasks import a2_exposure, a3_luck, a4_leak, a5_location, a8_decomposition, a9_verdicts
from tasks.a1_manager_list import manager_ten
from ui import BLUE, LIGHT_BLUE, card, detail, header, kpis, plot, section, summary, tile

@st.cache_data(show_spinner="Recalculating the machine review for this period. This takes about fifteen seconds.")
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
    n1 = len(ten) - int((ten["verdict"] == "Watch list").sum())
    n2 = n1 - int((ten["verdict"] == "Inspect").sum())
    n3 = int((ten["verdict"] == "Truly weak").sum())
    dropped = {
        "Enough time on the floor to judge": ", ".join(list(ten.loc[ten["verdict"] == "Watch list", "machine_id"]) + [f"{m} (not on the floor)" for m in missing]),
        "Payout settings appear correct": ", ".join(ten.loc[ten["verdict"] == "Inspect", "machine_id"]),
        "Not explained by other causes": ", ".join(
            f"{m} ({PLAIN_VERDICT.get(v, v)})" for m, v in zip(ten["machine_id"], ten["verdict"]) if v not in ("Watch list", "Inspect", "Truly weak"))}
    labels = ["On the proposed list", *dropped]
    values = [10, n1, n2, n3]
    fig = go.Figure(go.Bar(x=values[::-1], y=labels[::-1], orientation="h", text=[str(v) for v in values[::-1]], textposition="outside",
                           marker={"color": [LIGHT_BLUE, BLUE, BLUE, BLUE]},
                           customdata=["", *dropped.values()][::-1],
                           hovertemplate="%{y}: %{x}<br>Set aside at this step: %{customdata}<extra></extra>"))
    fig.update_xaxes(range=[0, 11], title_text="Machines remaining", dtick=1)
    fig.update_yaxes(automargin=True, showgrid=False)
    fig.update_layout(height=230)
    return fig


def luck_chart(base: pd.DataFrame, machine_id: str) -> go.Figure:
    d = base[base["machine_id"] == machine_id].sort_values("gaming_date")
    cum, band, x = d["luck_residual_usd"].cumsum(), 2 * np.sqrt(d["luck_var_usd2"].cumsum()), d["gaming_date"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.concat([x, x[::-1]]), y=pd.concat([band, -band[::-1]]), fill="toself", fillcolor="#e6eefc",
                             line={"width": 0}, hoverinfo="skip", name="Normal range for chance"))
    fig.add_trace(go.Scatter(x=x, y=cum, mode="lines", line={"color": BLUE, "width": 2}, name="Actual minus expected, running total",
                             hovertemplate="%{x|%b %d}: %{y:$,.0f}<extra></extra>"))
    fig.update_yaxes(tickformat="$,.0f")
    fig.update_layout(height=300)
    return fig


def pieces_chart(v: pd.Series) -> go.Figure:
    labels = {"short_exposure_usd": "Time on the floor", "downtime_usd": "Time out of service", "location_usd": "Location",
              "machine_volume_usd": "Machine: level of play", "machine_hold_usd": "Machine: game's share of wagers", "luck_usd": "Luck"}
    vals = [v[c] for c in labels]
    fig = go.Figure(go.Bar(x=vals, y=list(labels.values()), orientation="h", marker={"color": [BLUE if x < 0 else LIGHT_BLUE for x in vals]},
                           text=[money(x, signed=True) for x in vals], textposition="outside",
                           hovertemplate="%{y}: %{x:$,.0f}<extra></extra>"))
    fig.add_vline(x=0, line={"color": "#8a8a8a", "width": 1})
    span = max(abs(min(vals)), abs(max(vals))) * 1.35
    fig.update_xaxes(tickformat="$,.0f", range=[-span, span])
    fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
    fig.update_layout(height=300)
    return fig


def render() -> None:
    start, end = date_range()
    t = trial(start, end)
    v = t["verdicts"]
    ids = manager_ten()
    ten = v[v["in_manager_10"]]
    dec = t["dec"] if t["dec"] is not None else a8_decomposition.compute(t["base"], start, end, ids, t["location"])
    names = {"short_exposure_usd": "time on the floor", "downtime_usd": "time out of service", "location_usd": "location",
             "machine_volume_usd": "lower play on the machine", "machine_hold_usd": "the game's smaller share of each wager",
             "luck_usd": "luck"}
    totals = dec[dec["machine_id"].isin(ids)][list(names)].sum()
    main_cause, main_amount = names[totals.idxmin()], totals.min()
    header("Machine Review", "Assessment of the ten machines proposed for replacement, and of every machine on the floor")
    summary(
        "This page examines why each machine on the proposed list earned less than a typical machine. A machine can earn little "
        "for reasons that have nothing to do with the machine: it may have been installed late or removed early, been out of "
        "service, stood in a quiet part of the floor, run a game that keeps a smaller share of each wager, or simply had poor "
        "luck. Each of these causes is measured in dollars, and the parts add up exactly to the machine's total shortfall.\n\n"
        f"For the period shown, **{int((ten['verdict'] == 'Truly weak').sum())} of the ten machines** under-performs for reasons "
        f"attributable to the machine itself. Across the list, the largest single cause is **{main_cause}**, which accounts for "
        f"{money(abs(main_amount))} of the combined shortfall of {money(abs(dec[dec['machine_id'].isin(ids)]['gap_usd'].sum()))}. "
        "Nine of the ten machines stand in the Back Forty, the area with the lowest level of play on the floor."
        + ("" if is_full_window() else "\n\n*The figures on this page have been recalculated for the period selected in the sidebar. "
           "The proposed list itself remains the January–June list.*"))
    counts = ten["verdict"].value_counts()
    kpis([tile("Machines reviewed from the list", f"{len(ten)} of 10", "on the floor in this period", "fact_check", "blue"),
          tile("Machine under-performs", str(int(counts.get("Truly weak", 0))), "replacement may be justified", "swap_horiz", "orange"),
          tile("Explained by location", str(int(counts.get("Location", 0))), "the position, not the machine", "location_on", "purple"),
          tile("Game keeps less per wager", str(int(counts.get("Low-hold game", 0))), "well used, by design", "casino", "teal"),
          tile("Inspection advised", str(int(counts.get("Inspect", 0))), "payout pattern differs", "search", "red")])

    with card("Machines remaining after each check",
              "Machines are set aside if they have too little time on the floor, may have incorrect payout settings, or have a shortfall "
              "explained by location, luck, time on the floor or the game. Hover over a bar to see which machines were set aside."):
        plot(funnel(v))
    with card("Why each machine earned less than a typical machine",
              "Dollar amount attributable to each cause, January–June basis. The coloured parts add up to each machine's total shortfall (◆)."):
        fig = a8_decomposition.figure(dec, ids)
        plain = {"Short exposure": "Time on the floor", "Downtime": "Time out of service", "Machine: play volume": "Machine: level of play",
                 "Machine: game hold": "Machine: game's share of wagers", "Total gap vs typical": "Total difference"}
        for trace in fig.data:
            if trace.name in plain:
                trace.name = plain[trace.name]
        fig.update_xaxes(title_text="")
        fig.update_layout(legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "xanchor": "left"})
        plot(fig, height=470, legend_top=True)

    section("Findings for each machine")
    cols = {"machine_id": "Machine", "zone_name": "Area", "theme": "Game", "verdict": "Finding", "advice": "Recommendation"}
    tab1, tab2, tab3 = st.tabs(["The proposed list", "Machines we would consider replacing", "All machines (area and bank filters apply)"])
    with tab1:
        table(ten.assign(advice=ten["verdict"].map(PLAIN_ADVICE), verdict=ten["verdict"].map(PLAIN_VERDICT))[list(cols)].rename(columns=cols),
              column_config={"Recommendation": st.column_config.TextColumn(width=520)})
    with tab2:
        ours = v[v["on_our_list"]].sort_values("replace_rank")
        st.markdown(f"All {len(ours)} machines are the same game, **Comet Cash**. It is played less than its neighbouring machines "
                    "wherever it stands, which suggests replacing the game title rather than individual machines.")
        table(ours.assign(advice=ours["verdict"].map(PLAIN_ADVICE), verdict=ours["verdict"].map(PLAIN_VERDICT))[list(cols)].rename(columns=cols))
    with tab3:
        allv = zone_bank_filter(v)
        table(allv.assign(advice=allv["verdict"].map(PLAIN_ADVICE), verdict=allv["verdict"].map(PLAIN_VERDICT))[list(cols) + ["gap_usd"]].rename(columns=cols | {"gap_usd": "Difference from typical"}),
              column_config={"Difference from typical": st.column_config.NumberColumn(format="dollar")})

    section("Examine a single machine")
    present = set(v["machine_id"])
    order = [m for m in ids if m in present] + [m for m in v["machine_id"] if m not in ids]
    pick = st.selectbox("Machine", order, index=0, help="The ten machines on the proposed list are shown first.")
    r = v.set_index("machine_id").loc[pick]
    st.markdown(f"**{pick}**, {r['theme']}, in bank {r['bank_id']} ({r['zone_name']}). Finding: **{PLAIN_VERDICT.get(r['verdict'], r['verdict'])}**. {PLAIN_ADVICE.get(r['verdict'], r['advice'])}")
    kpis([tile("Expected win per available hour", money(r["tpah"], 2), "luck removed", "schedule", "blue"),
          tile("Compared with its neighbours", f"{r['peer_index']:.2f}×", "expected win, same bank, same days", "groups", "purple"),
          tile("Level of play vs neighbours", f"{r['volume_peer_index']:.2f}×", "amount wagered per hour", "casino", "teal"),
          tile("Difference from typical", money(r["gap_usd"], signed=True), "over the period", "compare_arrows", "orange")])
    a, b = st.columns(2)
    with a:
        with card("What accounts for the difference from a typical machine", "Negative amounts reduced earnings; positive amounts added to them", key="m_pieces"):
            plot(pieces_chart(r), key="pieces")
    with b:
        with card("Was it luck?", "Actual minus expected result, as a running total. Inside the shaded band, chance alone can explain it.", key="m_luck"):
            plot(luck_chart(t["base"], pick), key="luck", legend_top=True)

    with card("Expected win per hour by bank of machines", "Each dot is a bank; darker means higher. Orange rings mark banks holding a machine from the proposed list."):
        plot(a5_location.floor_map_figure(t["banks"]), height=560)

    with detail():
        st.markdown("**Terms.** *Expected win* is what the casino would expect to keep from the wagers placed, based on each game's "
                    "published payback percentage; it excludes luck. *Peer index* compares a machine with the other machines in its "
                    "bank over the same days. *Luck z* expresses the difference between actual and expected results in standard "
                    "deviations; values between −2 and +2 are within the normal range for chance.")
        e, l, k, loc = st.tabs(["Time on floor (A2)", "Luck (A3)", "Payout check (A4)", "Location (A5)"])
        with e:
            plot(a2_exposure.rank_shift_figure(t["exposure"]), height=420)
            evidence("A2-01")
        with l:
            plot(a3_luck.histogram_figure(t["luck"]), height=560)
            evidence("A3-01")
        with k:
            fig = a4_leak.cumulative_figure(t["base"], t["leak"], t["tickets"])
            if fig is not None:
                plot(fig, height=480)
            table(t["leak"][t["leak"]["inspection_lead"]][["machine_id", "reason"]])
            evidence(["A4-01", "A4-02"])
        with loc:
            table(zone_bank_filter(t["banks"])[["bank_id", "zone_name", "machines", "tpah", "occupancy", "bank_rank", "bank_quartile", "manager_10_machines"]],
                  column_config={"tpah": st.column_config.NumberColumn("Expected win per hour", format="dollar"),
                                 "occupancy": st.column_config.NumberColumn(format="percent")})
            evidence(["A5-01", "A5-02", "A5-03", "A6-01"])
        st.markdown("Full verdict table with every measure:")
        table(zone_bank_filter(v))
        evidence(["A1-01", "A8-01", "A9-01"])
