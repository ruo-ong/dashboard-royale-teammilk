"""Business forecast: how the daily forecast was chosen and tested, and the decision it informs."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import ROOT, evidence, money, out, pct, table
from ui import BLUE, LIGHT_BLUE, card, detail, header, key_points, kpis, plot, summary, tile


def render() -> None:
    sel = out("m3_selection")
    met = out("m4_metrics")
    res = out("forecast_results")
    allm = met[met["scope"] == "all test days"]
    chosen = allm[allm["model"].str.contains(r"\[chosen\]")].iloc[0]
    base_a = allm[allm["model"].str.startswith("Baseline A")].iloc[0]
    d = out("m5_decision")
    best = d[d["chosen"]].iloc[0]
    header("Business Forecast", "A forecast of the total amount wagered each day, how it was tested, and how it is used",
           chip="Chosen on Apr 2025 · tested on May–Jun 2025")
    kpis([tile("Forecasting method chosen", "Day-of-week average", "most accurate in April", "calendar_month", "blue"),
          tile("Average error, May–June", money(chosen["mae_usd"]), f"{pct(chosen['mape'], 1)} of a typical day", "target", "green"),
          tile("Error without day of week", money(base_a["mae_usd"]), "simple average, for comparison", "remove", "grey"),
          tile("Forecast for a July weekend", money(best["forecast_coin_in_usd"]), "amount wagered, Fri–Sun", "event", "purple")])
    more_text = (
        "To plan for July, we forecast the total amount wagered on the floor each day. We compared several forecasting methods "
        "using only information available on April 30, chose the most accurate on April's results, and then tested the chosen "
        "method once against what actually happened in May and June. The rules for this test were written down and recorded "
        "before any forecasting was done, so the result could not be adjusted after the fact.\n\n"
        f"The most accurate method was also the simplest: the **average for each day of the week**. In May and June its forecasts "
        f"differed from the actual amount wagered by an average of **{money(chosen['mae_usd'])} per day** ({pct(chosen['mape'], 1)} "
        f"of a typical day), compared with {money(base_a['mae_usd'])} for a forecast that ignores the day of the week. It tended to "
        f"forecast slightly too high in June, when business was lower.\n\n"
        f"The forecast is used to estimate the benefit of a promotion weekend in July (about {money(best['promo_theo_uplift_usd'])} in "
        "expected win per weekend) and provides the baseline against which the promotion's results will be measured.\n\n"
        "*This page does not change with the period selected in the sidebar, because the test period is fixed.*")
    key_points([
        "We forecast the **daily amount wagered** to plan for July.",
        "The method was chosen on April and **tested once** on May–June; the rules were recorded first.",
        f"The **day-of-week average** was most accurate: average error **{money(chosen['mae_usd'])} per day** ({pct(chosen['mape'], 1)}).",
        f"It sizes the **promotion weekend** benefit (about {money(best['promo_theo_uplift_usd'])}) and is the yardstick for measuring it.",
        f"Normal weekend forecast error was {pct(best['weekend_error_mean'], 1, True)} (± {pct(2 * best['weekend_error_sd'])}): an 18% lift "
        "would be detectable, a 6% lift would not.",
        f"**It changes the decision on success:** against a flat average, an ordinary weekend already looks "
        f"{pct(best['flat_baseline_false_lift'], 0, True)} better, so the simple baseline would call almost any promotion a success.",
        "*This page does not change with the sidebar period: the test period is fixed.*"
    ], more=more_text)

    with card("Forecast compared with what happened, May–June", "Daily amount wagered. Shaded: event days."):
        act = res.drop_duplicates("gaming_date")
        fig = go.Figure()
        for name, grp in act.dropna(subset=["event"]).groupby("event"):
            fig.add_vrect(x0=grp["gaming_date"].min(), x1=grp["gaming_date"].max() + pd.Timedelta(days=1), fillcolor="#e6eefc", opacity=1, line_width=0, layer="below")
        fig.add_trace(go.Bar(x=act["gaming_date"], y=act["actual"], name="Actual", marker={"color": LIGHT_BLUE},
                             hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra>Actual</extra>"))
        f = res[res["model"] == chosen["model"]]
        fig.add_trace(go.Scatter(x=f["gaming_date"], y=f["forecast"], mode="lines", name="Forecast (day-of-week average)",
                                 line={"color": BLUE, "width": 2.5}, hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra>Forecast</extra>"))
        fig.update_yaxes(tickformat="$,.3s")
        fig.update_layout(height=330, bargap=0.15)
        plot(fig, legend_top=True)
    a, b = st.columns(2)
    with a:
        with card("Accuracy of each method, May–June", "Average daily error. Lower is better."):
            shown = allm.assign(label=allm["model"].str.split(" \\(").str[0].str.replace(" [chosen]", " (chosen)", regex=False)
                                .str.replace("Baseline A: training mean", "Simple average").str.replace("Baseline B: weekday mean", "Day-of-week average")
                                .str.replace("Candidate 1: weekday mean x trend", "Day-of-week with trend").str.replace("Candidate 2: regression", "Regression with events"))
            shown = shown.sort_values("mae_usd")
            fig = go.Figure(go.Bar(x=shown["mae_usd"], y=shown["label"], orientation="h",
                                   marker={"color": [BLUE if "(chosen)" in l else LIGHT_BLUE for l in shown["label"]]},
                                   text=[money(v) for v in shown["mae_usd"]], textposition="outside",
                                   hovertemplate="%{y}: %{x:$,.0f} average daily error<extra></extra>"))
            fig.update_xaxes(tickformat="$,.0f", range=[0, shown["mae_usd"].max() * 1.25])
            fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
            fig.update_layout(height=260)
            plot(fig)
    with b:
        with card("How the forecast is used in the plan", None):
            st.markdown(d["decision"].iloc[0])

    with detail():
        st.markdown("**Procedure.** Target: daily floor coin-in. Candidates were fitted on January–March and compared on April; the chosen "
                    "method and both baselines were refitted on January–April and evaluated once on May–June, with every forecast "
                    "fixed as of April 30. Inputs were limited to information known on April 30 (weekday, holidays, announced events, "
                    "the scheduled closure, a trend); tourism, weather and survey data were excluded. The Locals Appreciation Week "
                    "(announced May 26) was not an input. The two rejected candidates are shown for transparency only.")
        with st.expander("The written protocol, recorded before any model code (docs/MODEL_PROTOCOL.md)"):
            st.markdown((ROOT / "docs" / "MODEL_PROTOCOL.md").read_text())
        table(sel, column_config={"mae_usd": st.column_config.NumberColumn("April MAE", format="dollar"),
                                  "bias_usd": st.column_config.NumberColumn("Bias", format="dollar"), "mape": st.column_config.NumberColumn("MAPE", format="percent")})
        table(met[met["model"] == chosen["model"]], column_config={"mae_usd": st.column_config.NumberColumn("MAE", format="dollar"),
                                                                    "bias_usd": st.column_config.NumberColumn("Bias", format="dollar")})
        table(d.drop(columns=["decision"]), column_config={c: st.column_config.NumberColumn(format="dollar") for c in d.columns if c.endswith("_usd")})
        evidence("M-01")
