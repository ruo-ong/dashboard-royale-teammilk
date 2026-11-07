"""Visitor demand (Q2): what changed in play across the floor over six months, and why."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import date_range, evidence, money, out, pct, table, zone_bank_filter
from ui import BLUE, LIGHT_BLUE, card, detail, header, kpis, plot, section, summary, tile


def _in(df, col="gaming_date"):
    s, e = date_range()
    return df[df[col].between(pd.Timestamp(s), pd.Timestamp(e))]


def trend() -> go.Figure:
    d = _in(out("b1_floor_trend"))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["gaming_date"], y=d["coin_in_usd"], name="Amount wagered each day", marker={"color": LIGHT_BLUE},
                         hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=d["gaming_date"], y=d["coin_in_usd_7d"], mode="lines", name="Seven-day average",
                             line={"color": BLUE, "width": 2.5}, hovertemplate="%{x|%b %d}: %{y:$,.0f}<extra></extra>"))
    fig.update_yaxes(tickformat="$,.3s")
    fig.update_layout(height=320, bargap=0.15)
    return fig


def events_fig() -> go.Figure:
    e = out("b2_event_uplift").sort_values("uplift_pct")
    names = e["event"].str.replace("College basketball tournament opening rounds", "College basketball tournament")
    fig = go.Figure(go.Bar(x=e["uplift_pct"], y=names, orientation="h",
                           marker={"color": [BLUE if s == "property" else LIGHT_BLUE for s in e["local_scope"]]},
                           text=[pct(v, 0, True) for v in e["uplift_pct"]], textposition="outside",
                           customdata=e[["uplift_usd", "days"]].to_numpy(),
                           hovertemplate="%{y}<br>%{x:+.0%} (%{customdata[0]:$,.0f} over %{customdata[1]} days)<extra></extra>"))
    fig.add_vline(x=0, line={"color": "#8a8a8a", "width": 1})
    fig.update_xaxes(tickformat="+.0%", range=[min(-0.02, e["uplift_pct"].min()) - 0.02, e["uplift_pct"].max() + 0.06])
    fig.update_yaxes(automargin=True, showgrid=False)
    fig.update_layout(height=330)
    return fig


def closure_fig() -> go.Figure:
    z = out("zone_day").copy()
    c = out("closure_effect").iloc[0]
    z["group"] = z["zone_id"].map(lambda x: "Back Forty" if x == "Z-B40" else "Rest of the floor")
    w = z.groupby(["week", "group"])[["theo_usd", "available_hours"]].sum().reset_index()
    w["tpah"] = w["theo_usd"] / w["available_hours"]
    fig = go.Figure()
    fig.add_vrect(x0=c["closed_from"], x1=pd.Timestamp(c["closed_through"]) + pd.Timedelta(days=1), fillcolor="#e6eefc", opacity=1, line_width=0, layer="below")
    fig.add_annotation(x=c["closed_from"], y=1, yref="paper", text="Walkway closed", showarrow=False, xanchor="left", yanchor="bottom",
                       font={"size": 11, "color": "#555"})
    for g, colour in [("Rest of the floor", LIGHT_BLUE), ("Back Forty", BLUE)]:
        s = w[w["group"] == g]
        fig.add_trace(go.Scatter(x=s["week"], y=s["tpah"], mode="lines+markers", name=g, line={"color": colour, "width": 2.5},
                                 marker={"size": 6}, hovertemplate="week of %{x|%b %d}: $%{y:.2f} per hour<extra>" + g + "</extra>"))
    fig.update_yaxes(tickformat="$.0f", title_text="Expected win per available hour")
    fig.update_layout(height=320)
    return fig


def zones_fig() -> go.Figure:
    z = zone_bank_filter(_in(out("zone_day")), bank_col=None)
    g = z.groupby("zone_name")[["theo_usd", "available_hours"]].sum()
    g = (g["theo_usd"] / g["available_hours"]).sort_values()
    fig = go.Figure(go.Bar(x=g.values, y=g.index, orientation="h", marker={"color": [BLUE if n == "Back Forty" else LIGHT_BLUE for n in g.index]},
                           text=[f"${v:.2f}" for v in g.values], textposition="outside",
                           hovertemplate="%{y}: $%{x:.2f} per available hour<extra></extra>"))
    fig.update_xaxes(tickformat="$.0f", range=[0, g.max() * 1.18])
    fig.update_yaxes(automargin=True, showgrid=False)
    fig.update_layout(height=300)
    return fig


def render() -> None:
    monthly = out("b1_monthly")
    c = out("closure_effect").iloc[0]
    ctx = out("b6_context")
    header("Visitor Demand", "How the level of play changed across the floor over the six months, and the reasons for the changes")
    summary(
        "Overall business was stable. The average amount wagered per day was "
        f"{money(monthly['coin_in_per_day'].iloc[0], 2)} in January and {money(monthly['coin_in_per_day'].iloc[-1], 2)} in June, and "
        "the casino's level of business followed the number of visitors to Las Vegas closely.\n\n"
        f"The largest change on the floor itself was the closure of the walkway between the Main Entrance and the Back Forty from "
        f"{pd.Timestamp(c['closed_from']):%B %-d} to {pd.Timestamp(c['closed_through']):%B %-d} for renovation. While it was closed, "
        f"play in the Back Forty fell by about {pct(abs(c['did_pct']))} compared with the rest of the floor, and foot traffic fell by a "
        f"similar amount. We estimate the closure cost about {money(c['theo_lost_usd'])} in expected win. Play returned to "
        "close to its earlier level after the walkway reopened, although the Back Forty remains the quietest area of the floor.\n\n"
        "Major sporting and festival weekends in the city increased play by 15% to 23%, and the casino's own promotion weekend "
        "increased it by 18%. Large conventions had no measurable effect.")
    first, last = monthly.iloc[0], monthly.iloc[-1]
    kpis([tile("Average wagered per day, June", money(last["coin_in_per_day"], 2), f"January: {money(first['coin_in_per_day'], 2)}", "payments", "blue"),
          tile("Change, January to June", pct(last["coin_in_per_day"] / first["coin_in_per_day"] - 1, 1, True), "amount wagered per day", "trending_flat", "purple"),
          tile("Back Forty during the closure", pct(c["did_pct"], 0, True), "play, relative to the rest of the floor", "do_not_disturb_on", "orange"),
          tile("Expected win lost to the closure", money(c["theo_lost_usd"]), f"range {money(c['theo_lost_low_usd'])}–{money(c['theo_lost_high_usd'])}", "money_off", "red"),
          tile("Busiest day of the week", "Saturday", "1.3 times an average day", "event", "green")])

    with card("Amount wagered across the floor, by day", "Daily totals with the seven-day average"):
        plot(trend(), legend_top=True)
    a, b = st.columns(2)
    with a:
        with card("Effect of events on the amount wagered", "Compared with the same weekday in the surrounding weeks. Dark blue: the casino's own promotions."):
            plot(events_fig())
    with b:
        with card("Expected win per available hour, by area", "For the period and areas selected. The Back Forty is highlighted."):
            plot(zones_fig())
    with card("The Back Forty before, during and after the walkway closure", "Expected win per available hour, by week"):
        plot(closure_fig(), legend_top=True)
    a, b = st.columns(2)
    with a:
        with card("The casino compared with Las Vegas", "Amount wagered per day and city visitors per day, each set to 100 in January"):
            fig = go.Figure()
            for col, name, colour in [("mean_visitors_per_calendar_day_index", "Las Vegas visitors per day", LIGHT_BLUE),
                                      ("coin_in_per_day_index", "Gilded Ace amount wagered per day", BLUE)]:
                fig.add_trace(go.Scatter(x=ctx["month"], y=ctx[col], mode="lines+markers", name=name, line={"color": colour, "width": 2.5},
                                         hovertemplate="%{x}: %{y:.1f}<extra>" + name + "</extra>"))
            fig.update_layout(height=300)
            plot(fig, legend_top=True)
    with b:
        with card("Busiest days of the week", "Average amount wagered on each weekday, compared with an average day (1.00)"):
            wd = out("b2_weekday")
            fig = go.Figure(go.Bar(x=wd["local_weekday"].str[:3], y=wd["index_vs_average"],
                                   marker={"color": [BLUE if v >= 1 else LIGHT_BLUE for v in wd["index_vs_average"]]},
                                   text=[f"{v:.2f}" for v in wd["index_vs_average"]], textposition="outside",
                                   hovertemplate="%{x}: %{y:.2f} times an average day<extra></extra>"))
            fig.update_yaxes(range=[0, 1.5])
            fig.update_layout(height=300)
            plot(fig)

    with detail():
        st.markdown("**The demand findings as stated in the evidence log:**")
        for r in out("b9_story").itertuples():
            st.markdown(f"- {r.sentence} `{r.claim_id}`")
        evidence(list(out("b9_story")["claim_id"]))
        st.markdown("**Event effects** (coin-in uplift vs the same weekday within four weeks; range is ±2 standard deviations of normal days):")
        table(out("b2_event_uplift")[["event", "local_scope", "start", "end", "announced_date", "uplift_usd", "uplift_pct", "uplift_low_usd", "uplift_high_usd", "theo_uplift_usd"]],
              column_config={c: st.column_config.NumberColumn(format="dollar") for c in ["uplift_usd", "uplift_low_usd", "uplift_high_usd", "theo_uplift_usd"]}
              | {"uplift_pct": st.column_config.NumberColumn(format="percent")})
        st.markdown("**Walkway closure: difference-in-differences** (Back Forty vs the rest of the floor):")
        table(out("closure_effect")[["metric", "period", "affected_before", "affected_period", "unaffected_before", "unaffected_period", "did_pct"]],
              column_config={"did_pct": st.column_config.NumberColumn("relative change", format="percent")})
        w = out("b6_weather")
        cs = out("b8_carded_share")
        t = out("b5_traffic_daily")
        st.markdown(f"- Weather: correlation of weekday-adjusted coin-in with maximum temperature "
                    f"{w[['coin_in_vs_weekday', 'tmax_c']].corr().iloc[0, 1]:+.2f}, with rainfall {w[['coin_in_vs_weekday', 'prcp_mm']].corr().iloc[0, 1]:+.2f}.\n"
                    f"- Loyalty-card share of coin-in: {pct(cs[cs['zone_name'] == 'All floor']['carded_share'].mean(), 1)} on average; "
                    f"{len(out('b8_carded_drops'))} machines had a short drop worth a card-reader check.\n"
                    f"- Door counters: {int(t['low_coverage'].sum())} of {len(t):,} sensor-days had low coverage and are excluded; "
                    "offline hours are treated as missing, never zero. Counts are entries, not unique visitors.")
