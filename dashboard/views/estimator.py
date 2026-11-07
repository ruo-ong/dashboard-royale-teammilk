"""Machine estimator (version 2 only): estimate how a machine with given characteristics would be expected to perform."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from common import evidence, money, out, pct, table
from tasks.m6_machine_model import estimate
from ui import BLUE, LIGHT_BLUE, card, detail, header, kpis, plot, section, summary, tile

LEASE = {"owned": "Owned by the casino", "leased_fixed": "Leased, fixed daily fee", "leased_revenue_share": "Leased, share of winnings"}


def _effect(coef, kind: str, term: str) -> float:
    row = coef[(coef["term_type"] == kind) & (coef["term"] == term)]
    return float(np.exp(row["coef"].iloc[0]) - 1) if len(row) else 0.0


def render() -> None:
    games = out("m6_games").set_index("config_id")
    banks = out("bank_scores")
    coef = out("m6_coefficients")
    val = out("m6_validation")
    verdicts = out("machine_verdicts").set_index("machine_id")
    profit = out("a11_profit").set_index("machine_id")
    exposure = out("a2_exposure").set_index("machine_id")

    header("Machine Estimator", "Estimate the expected earnings of a machine before placing, moving or replacing it", chip="Version 2 tool")
    est_row = val.iloc[0]
    bank_row = val[val["method"].str.contains("bank")].iloc[0]
    summary(
        "This tool estimates how much a machine would be expected to earn, given its game, its position on the floor, its "
        "manufacturer and its lease arrangement. It can be used to compare options before a machine is placed, moved or replaced. "
        "You may start from a machine already on the floor and change one characteristic at a time, for example its location.\n\n"
        "The estimate is based on the performance of every machine on the floor from January to June 2025. When the estimator was "
        f"built using January–April records only and then checked against May–June, its estimates differed from actual results by an "
        f"average of **{money(est_row['mae_per_hour_usd'], 2)} per hour** ({pct(est_row['mape'], 1)}), compared with "
        f"{money(bank_row['mae_per_hour_usd'], 2)} per hour ({pct(bank_row['mape'], 1)}) when using the average of the machine's bank. "
        "The estimate describes expected earnings before luck; the amount actually kept in any month will vary around it, and the "
        "likely range of that variation is shown below. Estimates for combinations that do not exist on the floor today (for example, "
        "a game that has never stood in a given area) rely on the separate effects of the game and the location and should be "
        "treated with additional caution.")

    with st.container(key="card_inputs"):
        st.markdown('<div class="card-t">Describe the machine</div><div class="card-s">All results update as you change the inputs</div>',
                    unsafe_allow_html=True)
        mode = st.radio("Starting point", ["A machine already on the floor", "A new machine"], horizontal=True)
        base_id = None
        if mode == "A machine already on the floor":
            base_id = st.selectbox("Machine", list(verdicts.index), index=list(verdicts.index).index("M-1181"),
                                   help="Its current characteristics are filled in below; you may change any of them.")
        cfg_list = list(games.index)
        default_cfg = exposure.loc[base_id, "config_id"] if base_id else "G-STD90"
        default_bank = verdicts.loc[base_id, "bank_id"] if base_id else "B-12"
        default_maker = profit.loc[base_id, "manufacturer"] if base_id else "Northwind"
        default_lease = profit.loc[base_id, "lease_class"] if base_id else "owned"
        default_avail = float(exposure.loc[base_id, "availability"]) if base_id else 0.997
        k = base_id or "new"
        c1, c2, c3 = st.columns(3)
        game = c1.selectbox("Game", cfg_list, index=cfg_list.index(default_cfg), key=f"g_{k}",
                            format_func=lambda c: f"{games.loc[c, 'theme']} (pays back {games.loc[c, 'configured_rtp']:.0%}, {games.loc[c, 'volatility_class'].replace('_', ' ')} volatility)")
        zones = sorted(banks["zone_name"].unique())
        default_zone = banks.set_index("bank_id").loc[default_bank, "zone_name"]
        zone = c2.selectbox("Area of the floor", zones, index=zones.index(default_zone), key=f"z_{k}")
        bank_opts = sorted(banks.loc[banks["zone_name"] == zone, "bank_id"])
        bank = c3.selectbox("Bank of machines", bank_opts, index=bank_opts.index(default_bank) if default_bank in bank_opts else 0, key=f"b_{k}")
        c1, c2, c3 = st.columns(3)
        makers = sorted(coef.loc[coef["term_type"] == "manufacturer", "term"])
        maker = c1.selectbox("Manufacturer", makers, index=makers.index(default_maker), key=f"m_{k}")
        lease = c2.selectbox("Ownership", list(LEASE), index=list(LEASE).index(default_lease), format_func=LEASE.get, key=f"l_{k}")
        avail = c3.slider("Expected time in working order", 0.90, 1.00, round(default_avail, 3), 0.001, format="%.3f", key=f"a_{k}",
                          help="The share of the period the machine is expected to be working. The floor median is 0.997 (99.7%).")
        c1, c2 = st.columns(2)
        days = c1.slider("Length of the period (days)", 7, 90, 30)
        july = c2.checkbox("Adjust for the expected level of business in July (from the business forecast)", value=True)

    e = estimate(game, bank, maker, lease, avail, days, july)
    floor_tpah = out("machine_verdicts")["tpah"]
    comparable = e["tpah"] / e["demand_factor"]
    rank = (floor_tpah < comparable).mean()
    bank_now = float(banks.set_index("bank_id").loc[bank, "tpah"])
    loc_eff, game_eff, maker_eff = _effect(coef, "bank", bank), _effect(coef, "game", game), _effect(coef, "manufacturer", maker)

    section("Estimated performance")
    kpis([tile("Expected win per working hour", money(e["tpah"], 2), f"range {money(e['tpah_low'], 2)}–{money(e['tpah_high'], 2)}", "schedule", "blue"),
          tile(f"Expected win over {days} days", money(e["expected_win"]), f"range {money(e['expected_win_low'])}–{money(e['expected_win_high'])}", "payments", "green"),
          tile("Likely result including luck", f"{money(e['house_win_low'])}–{money(e['house_win_high'])}", "in about 19 periods out of 20", "casino", "purple"),
          tile("Running costs", money(e["total_costs"]), f"lease, service, power, repairs ({days} days)", "receipt_long", "orange"),
          tile("Expected contribution", money(e["contribution"]), "expected win minus running costs", "account_balance", "teal"),
          tile("Compared with the floor", f"Higher than {pct(rank)}", "of machines, per working hour", "leaderboard", "yellow")])

    text = (f"A **{games.loc[game, 'theme']}** machine made by {maker}, in bank {bank} ({zone}), {LEASE[lease].lower()}, would be expected to "
            f"earn about **{money(e['tpah'], 2)} for each hour it is in working order**. Over {days} days at "
            f"{pct(avail, 1)} availability, that is about **{money(e['expected_win'])}** in expected win, with an estimated range of "
            f"{money(e['expected_win_low'])} to {money(e['expected_win_high'])}. The amount the casino actually keeps will also depend on "
            f"luck; for this game and level of play it would fall between {money(e['house_win_low'])} and {money(e['house_win_high'])} in "
            f"about 19 periods out of 20. After running costs of {money(e['total_costs'])}, the expected contribution is "
            f"**{money(e['contribution'])}**. Per working hour, this would place the machine above {pct(rank)} of the machines on the floor today.")
    if base_id:
        actual = verdicts.loc[base_id, "tpah"]
        text += (f"\n\nFor comparison, {base_id} actually earned {money(actual, 2)} per working hour in January–June in its current position "
                 f"({verdicts.loc[base_id, 'bank_id']}).")
    summary(text, key="estimate")

    a, b = st.columns(2)
    with a:
        with card("How this estimate compares", "Expected win per working hour (January–June level)"):
            rows = [("This estimate", comparable, BLUE), (f"Machines now in bank {bank}", bank_now, LIGHT_BLUE),
                    ("Typical machine on the floor", float(floor_tpah.median()), LIGHT_BLUE)]
            if base_id:
                rows.append((f"{base_id}, actual January–June", float(verdicts.loc[base_id, "tpah"]), LIGHT_BLUE))
            fig = go.Figure(go.Bar(x=[r[1] for r in rows], y=[r[0] for r in rows], orientation="h", marker={"color": [r[2] for r in rows]},
                                   text=[money(r[1], 2) for r in rows], textposition="outside",
                                   hovertemplate="%{y}: $%{x:.2f} per working hour<extra></extra>"))
            fig.update_xaxes(tickformat="$.0f", range=[0, max(r[1] for r in rows) * 1.25])
            fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
            fig.update_layout(height=260)
            plot(fig)
    with b:
        with card("What drives the estimate", "Effect of each characteristic compared with an average machine on this floor"):
            parts = [("Location (bank " + bank + ")", loc_eff), (f"Game ({games.loc[game, 'theme']})", game_eff), (f"Manufacturer ({maker})", maker_eff)]
            if july:
                parts.append(("July level of business", e["demand_factor"] - 1))
            fig = go.Figure(go.Bar(x=[p[1] for p in parts], y=[p[0] for p in parts], orientation="h",
                                   marker={"color": [BLUE if p[1] >= 0 else LIGHT_BLUE for p in parts]},
                                   text=[pct(p[1], 0, True) for p in parts], textposition="outside",
                                   hovertemplate="%{y}: %{x:+.0%}<extra></extra>"))
            span = max(0.1, max(abs(p[1]) for p in parts) * 1.4)
            fig.add_vline(x=0, line={"color": "#8a8a8a", "width": 1})
            fig.update_xaxes(tickformat="+.0%", range=[-span, span])
            fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
            fig.update_layout(height=260)
            plot(fig)

    with card("Running costs for the period", "Based on the cost rules supplied with the data. Revenue-share leases are estimated from expected win."):
        c = e["costs"]
        table([{"Cost": k.capitalize(), "Amount": v} for k, v in c.items()] + [{"Cost": "Total", "Amount": e["total_costs"]}],
              column_config={"Amount": st.column_config.NumberColumn(format="dollar")})

    with detail("How the estimator works and how it was tested (for analysts)"):
        st.markdown(
            "**Model.** log(expected win per available hour) = baseline + bank effect + game effect + manufacturer effect, fitted by "
            "weighted least squares (weights = available hours) with a ridge penalty of 1.0, so that banks with few machines are drawn "
            "toward the floor average. Expected win over a period = rate × 24 × days × availability. The luck range is ±2 standard "
            "deviations, using the game's payout variance per dollar wagered. The estimate range is the 10th to 90th percentile of the "
            "test errors around their median; the overall change in the level of business between periods is handled separately by "
            "the July demand factor taken from the floor forecast (M5).")
        table(val, column_config={"mae_per_hour_usd": st.column_config.NumberColumn("MAE per hour", format="dollar"),
                                  "bias_per_hour_usd": st.column_config.NumberColumn("Bias per hour", format="dollar"),
                                  "mae_30_days_usd": st.column_config.NumberColumn("MAE over 30 days", format="dollar"),
                                  "mape": st.column_config.NumberColumn("MAPE", format="percent")})
        p = out("m6_test_predictions")
        fig = go.Figure(go.Scatter(x=p["model_tpah"], y=p["tpah"], mode="markers", marker={"color": BLUE, "size": 6, "opacity": 0.7},
                                   text=p["machine_id"], hovertemplate="%{text}<br>estimated $%{x:.2f}, actual $%{y:.2f}<extra></extra>"))
        lim = [0, max(p["model_tpah"].max(), p["tpah"].max()) * 1.05]
        fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines", line={"color": "#b5b5b5", "dash": "dot"}, hoverinfo="skip", showlegend=False))
        fig.update_xaxes(title_text="Estimated (fitted on January–April)", tickformat="$.0f")
        fig.update_yaxes(title_text="Actual, May–June", tickformat="$.0f")
        fig.update_layout(height=360, showlegend=False)
        st.markdown(f"Estimated vs actual expected win per available hour for {len(p)} machines in May–June "
                    f"({pct(p['within_80pct_range'].mean())} fell inside the stated 80% range):")
        plot(fig, key="m6_scatter")
        table(coef, column_config={"multiplier": st.column_config.NumberColumn(format="%.3f"), "coef": st.column_config.NumberColumn(format="%.3f")})
        evidence(["M6-01", "M-01"])
