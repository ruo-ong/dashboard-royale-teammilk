"""W4 - Q2, demand: what changed across the floor over six months, and why."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import COLORS, chart, date_range, evidence, filter_note, money, out, pct, style, table, zone_bank_filter


def _in(df, col="gaming_date"):
    s, e = date_range()
    return df[df[col].between(pd.Timestamp(s), pd.Timestamp(e))]


def trend() -> go.Figure:
    d = _in(out("b1_floor_trend"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["gaming_date"], y=d["coin_in_usd"], mode="markers", name="Daily coin-in",
                             marker={"size": 5, "color": COLORS["neutral"]}, hovertemplate="%{x|%a %b %d}: %{y:$,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=d["gaming_date"], y=d["coin_in_usd_7d"], mode="lines", name="7-day average",
                             line={"color": COLORS["series_1"], "width": 2}, hovertemplate="%{x|%b %d}: %{y:$,.0f}<extra></extra>"))
    ev = out("b2_event_uplift")
    for r in ev.itertuples():
        if pd.Timestamp(r.end) >= d["gaming_date"].min() and pd.Timestamp(r.start) <= d["gaming_date"].max():
            fig.add_vrect(x0=r.start, x1=pd.Timestamp(r.end) + pd.Timedelta(days=1), fillcolor=COLORS["grid"], opacity=0.5, line_width=0)
    first, last = d["coin_in_usd_7d"].dropna().iloc[[0, -1]]
    style(fig, f"Floor coin-in was broadly flat ({pct(last / first - 1, 1, True)} over the period, 7-day average)",
          "Daily coin-in in dollars; grey bands are event days", height=380)
    fig.update_yaxes(tickformat="$,.3s")
    fig.update_layout(legend={"y": -0.2, "x": 0, "xanchor": "left"})
    return fig


def events_fig() -> go.Figure:
    e = out("b2_event_uplift").sort_values("uplift_pct")
    fig = go.Figure()
    for scope, colour, name in [("citywide", COLORS["series_1"], "Citywide event"), ("property", COLORS["series_2"], "Our own promotion")]:
        s = e[e["local_scope"] == scope]
        lo = s["uplift_low_usd"] / s["baseline_coin_in_usd"]
        hi = s["uplift_high_usd"] / s["baseline_coin_in_usd"]
        fig.add_trace(go.Scatter(x=s["uplift_pct"], y=s["event"], mode="markers", name=name,
                                 marker={"size": 11, "color": colour, "line": {"color": COLORS["surface"], "width": 2}},
                                 error_x={"type": "data", "symmetric": False, "array": hi - s["uplift_pct"],
                                          "arrayminus": s["uplift_pct"] - lo, "color": colour, "thickness": 2, "width": 0},
                                 customdata=s[["uplift_usd", "days"]].to_numpy(),
                                 hovertemplate="%{y}<br>%{x:+.0%} coin-in (%{customdata[0]:$,.0f} over %{customdata[1]} days)<extra></extra>"))
    fig.add_vline(x=0, line={"color": COLORS["text_secondary"], "width": 1})
    style(fig, "Sports weekends and our promotions lift play",
          "Coin-in vs the same weekday nearby (bars: ±2 SD); conventions show no effect", height=400)
    fig.update_xaxes(tickformat="+.0%", title_text="Uplift in coin-in")
    fig.update_yaxes(showgrid=False, automargin=True)
    fig.update_layout(legend={"y": -0.35, "x": 0, "xanchor": "left"})
    return fig


def closure_fig() -> go.Figure:
    z = out("zone_day").copy()
    c = out("closure_effect").iloc[0]
    z["group"] = z["zone_id"].map(lambda x: "Back Forty (lost its walkway)" if x == "Z-B40" else "Rest of the floor")
    w = z.groupby(["week", "group"])[["theo_usd", "available_hours"]].sum().reset_index()
    w["tpah"] = w["theo_usd"] / w["available_hours"]
    fig = go.Figure()
    fig.add_vrect(x0=c["closed_from"], x1=pd.Timestamp(c["closed_through"]) + pd.Timedelta(days=1), fillcolor=COLORS["grid"],
                  opacity=0.7, line_width=0)
    fig.add_annotation(x=c["closed_from"], y=1, yref="paper", text="walkway closed", showarrow=False, xanchor="left",
                       yanchor="bottom", font={"size": 12, "color": COLORS["text_secondary"]})
    for g, colour in [("Rest of the floor", COLORS["neutral"]), ("Back Forty (lost its walkway)", COLORS["series_1"])]:
        s = w[w["group"] == g]
        fig.add_trace(go.Scatter(x=s["week"], y=s["tpah"], mode="lines+markers", name=g, line={"color": colour, "width": 2},
                                 marker={"size": 6}, hovertemplate="week of %{x|%b %d}: $%{y:.2f}/h<extra>" + g + "</extra>"))
    style(fig, f"The Back Forty lost {pct(abs(c['did_pct']))} of its play value while its walkway was closed, then recovered",
          f"Theo per available hour by week. Difference-in-differences vs the rest of the floor; "
          f"≈{money(c['theo_lost_usd'])} theo lost ({money(c['theo_lost_low_usd'])}–{money(c['theo_lost_high_usd'])})", height=380)
    fig.update_yaxes(tickformat="$.0f", title_text="TPAH")
    fig.update_layout(legend={"y": -0.2, "x": 0, "xanchor": "left"})
    return fig


def zones_fig() -> go.Figure:
    z = zone_bank_filter(_in(out("zone_day")), bank_col=None)
    w = z.groupby(["zone_name", "week"])[["theo_usd", "available_hours"]].sum().reset_index()
    w["tpah"] = w["theo_usd"] / w["available_hours"]
    palette = [COLORS[f"series_{i}"] for i in range(1, 7)] + ["#6250d6"]
    names = sorted(w["zone_name"].unique(), key=lambda n: -w[w["zone_name"] == n]["tpah"].mean())
    fig = go.Figure()
    for i, n in enumerate(names):
        s = w[w["zone_name"] == n]
        fig.add_trace(go.Scatter(x=s["week"], y=s["tpah"], mode="lines", name=n, line={"color": palette[i % len(palette)], "width": 2},
                                 hovertemplate="week of %{x|%b %d}: $%{y:.2f}/h<extra>" + n + "</extra>"))
    style(fig, "The Back Forty earns the least per hour in every week; the gap is not just the closure",
          "Theo per available hour by zone and week (legend ordered by average)", height=400)
    fig.update_yaxes(tickformat="$.0f")
    return fig


def city_fig() -> go.Figure:
    c = out("b6_context")
    fig = go.Figure()
    for col, name, colour in [("mean_visitors_per_calendar_day_index", "Las Vegas visitors per day", COLORS["neutral"]),
                              ("coin_in_per_day_index", "Gilded Ace coin-in per day", COLORS["series_1"])]:
        fig.add_trace(go.Scatter(x=c["month"], y=c[col], mode="lines+markers", name=name, line={"color": colour, "width": 2},
                                 hovertemplate="%{x}: %{y:.1f}<extra>" + name + "</extra>"))
    gap = c["coin_in_per_day_index"].iloc[-1] - c["mean_visitors_per_calendar_day_index"].iloc[-1]
    style(fig, f"The casino tracked the city ({gap:+.1f} pts by June)",
          "Index, Jan = 100. LVCVA data: all of Las Vegas, published later", height=340)
    fig.update_layout(legend={"y": -0.25, "x": 0, "xanchor": "left"})
    return fig


def render() -> None:
    st.title("Q2 · What changed in demand, and why")
    filter_note()
    with st.container(border=True):
        st.markdown("**The demand story**")
        for r in out("b9_story").itertuples():
            st.markdown(f"- {r.sentence} `{r.claim_id}`")
        evidence(list(out("b9_story")["claim_id"]), "Evidence for each sentence")
    chart(trend())
    a, b = st.columns(2)
    with a:
        chart(events_fig())
    with b:
        wd = out("b2_weekday")
        fig = go.Figure(go.Bar(x=wd["local_weekday"].str[:3], y=wd["index_vs_average"], marker={"color": COLORS["series_1"]},
                               text=[f"{v:.2f}" for v in wd["index_vs_average"]], textposition="outside",
                               hovertemplate="%{x}: %{y:.2f}× an average day<extra></extra>"))
        style(fig, "Saturdays bring 1.3× an average day", "Coin-in by weekday ÷ average (events and holidays excluded)", height=400)
        fig.update_yaxes(range=[0, 1.5])
        chart(fig)
    chart(closure_fig())
    evidence(["B9-03", "A5-01"])
    chart(zones_fig())
    a, b = st.columns(2)
    with a:
        chart(city_fig())
    with b:
        cs = out("b8_carded_share")
        floor = cs[cs["zone_name"] == "All floor"]
        st.markdown("**Other checks**")
        st.markdown(f"- Weather barely matters: correlation of weekday-adjusted coin-in with max temperature "
                    f"{out('b6_weather')[['coin_in_vs_weekday', 'tmax_c']].corr().iloc[0, 1]:+.2f}, with rain "
                    f"{out('b6_weather')[['coin_in_vs_weekday', 'prcp_mm']].corr().iloc[0, 1]:+.2f}.")
        st.markdown(f"- Loyalty-card share of coin-in held at {pct(floor['carded_share'].mean(), 1)} all period "
                    f"({len(out('b8_carded_drops'))} machines had a short drop worth a card-reader check).")
        t = out("b5_traffic_daily")
        st.markdown(f"- Door counters: {int(t['low_coverage'].sum())} of {len(t):,} sensor-days had low coverage and are left out; "
                    "offline hours are missing, never zero. Counts are entries, not unique visitors.")
