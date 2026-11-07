"""W8 - the forecast model: protocol, validation, results, and the decision (judge task 3)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, ROOT, chart, evidence, money, out, pct, style, table


def render() -> None:
    st.title("Forecast model: how it was validated")
    st.info("This page does not follow the sidebar's date filter on purpose: the model was chosen on April and tested once on "
            "May–June with forecasts frozen as of April 30. Re-cutting the period would reopen the test set.", icon=":material/lock:")
    sel = out("m3_selection")
    met = out("m4_metrics")
    res = out("forecast_results")
    allm = met[met["scope"] == "all test days"]
    chosen = allm[allm["model"].str.contains(r"\[chosen\]")].iloc[0]
    base_a = allm[allm["model"].str.startswith("Baseline A")].iloc[0]
    k = st.columns(4)
    kpi(k[0], "Chosen model", chosen["model"].split(": ")[1].replace(" [chosen]", ""))
    kpi(k[1], "Test MAE (May–June)", money(chosen["mae_usd"]), f"{pct(chosen['mape'], 1)} of a day's coin-in")
    kpi(k[2], "Constant-mean baseline MAE", money(base_a["mae_usd"]))
    kpi(k[3], "Bias (forecast − actual)", money(chosen["bias_usd"], signed=True), "per day")

    st.subheader("1 · The protocol, frozen before any model code")
    st.markdown("Target: daily floor coin-in. Choose on April (fit January–March); refit on January–April; test once on May–June. "
                "Inputs limited to what was known on April 30: weekday, holidays, announced events, the scheduled closure, a trend. "
                "No tourism, weather actuals or survey data. The Locals Appreciation Week (announced May 26) is **not** an input.")
    with st.expander("Read the full protocol (docs/MODEL_PROTOCOL.md)"):
        st.markdown((ROOT / "docs" / "MODEL_PROTOCOL.md").read_text())

    st.subheader("2 · Choosing on April")
    table(sel.rename(columns={"mae_usd": "April MAE", "mape": "MAPE", "bias_usd": "Bias"}),
          column_config={"April MAE": st.column_config.NumberColumn(format="dollar"), "Bias": st.column_config.NumberColumn(format="dollar"),
                         "MAPE": st.column_config.NumberColumn(format="percent")})
    st.caption("Both richer candidates over-extrapolated the January–March rise, so the weekday average won. The protocol says: "
               "if no candidate beats the weekday baseline in April, the weekday baseline is the model.")

    st.subheader("3 · One test on May–June")
    fig = go.Figure()
    act = res.drop_duplicates("gaming_date")
    fig.add_trace(go.Scatter(x=act["gaming_date"], y=act["actual"], mode="lines+markers", name="Actual",
                             line={"color": COLORS["text"], "width": 2}, marker={"size": 4},
                             hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra>Actual</extra>"))
    for model, colour in [(chosen["model"], COLORS["series_1"]), (base_a["model"], COLORS["neutral"])]:
        f = res[res["model"] == model]
        fig.add_trace(go.Scatter(x=f["gaming_date"], y=f["forecast"], mode="lines", name=model.split(": ")[1],
                                 line={"color": colour, "width": 2, "dash": "solid" if colour == COLORS["series_1"] else "dot"},
                                 hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra></extra>"))
    for name, grp in act.dropna(subset=["event"]).groupby("event"):
        fig.add_vrect(x0=grp["gaming_date"].min(), x1=grp["gaming_date"].max() + pd.Timedelta(days=1), fillcolor=COLORS["grid"], opacity=0.6, line_width=0)
    style(fig, f"The weekday average follows the weekly rhythm; it misses event weekends and the June dip",
          "Daily floor coin-in, May–June. Grey bands: EDC (an input) and Locals Week (not known on April 30)", height=420)
    fig.update_yaxes(tickformat="$,.2s")
    fig.update_layout(legend={"y": -0.28, "x": 0, "xanchor": "left"})
    chart(fig)
    shown = allm.assign(model=allm["model"].str.split(" \\(").str[0].str.replace(" [chosen]", " ✓ chosen", regex=False))
    table(shown[["model", "mae_usd", "mape", "bias_usd"]],
          column_config={"mae_usd": st.column_config.NumberColumn("MAE", format="dollar"), "bias_usd": st.column_config.NumberColumn("Bias", format="dollar"),
                         "mape": st.column_config.NumberColumn("MAPE", format="percent")})
    st.caption("Candidates 1 and 2 were ruled out in April; their May–June numbers are shown for transparency only.")
    with st.expander("Error by weekday (chosen model)"):
        wd = met[(met["model"] == chosen["model"]) & (met["scope"] != "all test days")]
        table(wd[["scope", "mae_usd", "bias_usd"]].rename(columns={"scope": "weekday"}),
              column_config={"mae_usd": st.column_config.NumberColumn("MAE", format="dollar"), "bias_usd": st.column_config.NumberColumn("Bias", format="dollar")})

    st.subheader("4 · The decision it drives")
    d = out("m5_decision")
    st.success(d["decision"].iloc[0], icon=":material/event:")
    table(d[["weekend", "eligible_after_lead", "forecast_coin_in_usd", "forecast_theo_usd", "promo_theo_uplift_low_usd",
             "promo_theo_uplift_usd", "promo_theo_uplift_high_usd", "chosen"]],
          column_config={c: st.column_config.NumberColumn(format="dollar") for c in
                         ["forecast_coin_in_usd", "forecast_theo_usd", "promo_theo_uplift_low_usd", "promo_theo_uplift_usd", "promo_theo_uplift_high_usd"]})
    evidence("M-01")
