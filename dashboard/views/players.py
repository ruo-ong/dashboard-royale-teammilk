"""W6 - Q4, tracked players: wagered, got back, net, and how concentrated. Drill into any guest group (judge task 2)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import kpi, COLORS, chart, date_range, evidence, money, out, pct, style, table, tracked_label
from tasks import d_players


@st.cache_data(show_spinner="Summing tracked play for these months...")
def totals(months: tuple[str, ...]) -> pd.DataFrame:
    return d_players.player_totals(list(months))


def render() -> None:
    st.title("Q4 · Tracked players: what they wagered, got back and netted")
    tracked_label()
    s, e = date_range()
    months = tuple(d_players.months_in(s, e))
    pt = out("player_totals") if len(months) == 6 else totals(months)

    with st.container(border=True):
        st.markdown("**Guest group** (filters apply to everything below)")
        c = st.columns(4)
        picks = {}
        for col, (dim, label) in zip(c, [("age_band", "Age band"), ("home_region", "Home region"),
                                         ("opening_tier", "Tier at Jan 1"), ("tier_end", "Tier at the end")]):
            picks[dim] = col.multiselect(label, sorted(pt[dim].dropna().unique()), key=f"p_{dim}")
    g = pt[pt["gamed"]]
    for dim, vals in picks.items():
        if vals:
            g = g[g[dim].isin(vals)]
    st.caption(f"Months: {', '.join(months)} · {len(g):,} players with carded play in this group")
    if g.empty:
        st.warning("No players in this group.")
        return

    k = st.columns(5)
    kpi(k[0], "Tracked coin-in", money(g["tracked_coin_in_usd"].sum()))
    kpi(k[1], "Got back (payout)", money(g["tracked_payout_usd"].sum()))
    kpi(k[2], "Players' net", money(g["tracked_net_usd"].sum()))
    kpi(k[3], "Came out ahead", pct(g["ahead"].mean(), 1))
    kpi(k[4], "Median player net", money(g["tracked_net_usd"].median()))
    evidence("D-01")

    a, b = st.columns(2)
    with a:
        edges = [-np.inf, -5000, -1000, -500, -250, -100, -50, -10, 0, 10, 50, 100, 250, 500, 1000, np.inf]
        labels = ["< −$5k", "−$5k…−$1k", "−$1k…−$500", "−$500…−$250", "−$250…−$100", "−$100…−$50", "−$50…−$10", "−$10…$0",
                  "$0…$10", "$10…$50", "$50…$100", "$100…$250", "$250…$500", "$500…$1k", "> $1k"]
        counts = pd.cut(g["tracked_net_usd"], edges, labels=labels, right=False).value_counts().reindex(labels)
        colours = [COLORS["series_2"] if l.startswith(("<", "−")) else COLORS["series_1"] for l in labels]
        fig = go.Figure(go.Bar(x=labels, y=counts.to_numpy(), marker={"color": colours},
                               hovertemplate="%{x}: %{y:,} players<extra></extra>"))
        style(fig, f"Most tracked players lose a little; {pct(g['ahead'].mean())} come out ahead",
              "Players by tracked net result (orange = lost, blue = won)", height=440)
        fig.update_xaxes(tickangle=-45)
        fig.update_layout(margin={"b": 120})
        chart(fig)
    with b:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line={"color": COLORS["neutral"], "dash": "dot", "width": 1},
                                 name="Perfect equality", hoverinfo="skip"))
        tops = {}
        for name, values, colour in [("Theo (expected loss)", g["theo_usd"].to_numpy(), COLORS["series_1"]),
                                     ("Actual losses (losing players)", (-g.loc[~g["ahead"], "tracked_net_usd"]).to_numpy(), COLORS["series_2"])]:
            cum, gini = d_players._lorenz(values)
            x = np.linspace(0, 1, len(cum))
            idx = np.linspace(0, len(cum) - 1, 200).astype(int)
            fig.add_trace(go.Scatter(x=x[idx], y=cum[idx], mode="lines", name=f"{name} · Gini {gini:.2f}", line={"color": colour, "width": 2},
                                     hovertemplate="bottom %{x:.0%} of players: %{y:.0%}<extra></extra>"))
            desc = np.sort(values)[::-1]
            tops[name] = desc[: max(1, int(0.1 * len(desc)))].sum() / desc.sum()
        style(fig, f"The top 10% of players produce {pct(tops['Theo (expected loss)'])} of tracked theo",
              "Lorenz curves: share of the total held by the bottom x% of players", height=380)
        fig.update_xaxes(tickformat=".0%", title_text="Share of players (lightest first)")
        fig.update_yaxes(tickformat=".0%")
        fig.update_layout(height=440, legend={"y": 0.98, "yanchor": "top", "x": 0.02, "xanchor": "left", "bgcolor": "rgba(252,252,251,0.9)"})
        chart(fig)
    evidence("D-02")

    dec = d_players.luck_by_decile(g) if len(g) >= 10 else None
    if dec is not None:
        fig = go.Figure(go.Bar(x=[f"D{d}" for d in dec["decile"]], y=dec["share_ahead"], marker={"color": COLORS["series_1"]},
                               text=[pct(v) for v in dec["share_ahead"]], textposition="outside",
                               customdata=dec[["coin_in_min", "coin_in_max", "net_per_player_usd", "expected_net_per_player_usd"]].to_numpy(),
                               hovertemplate="%{x}: %{y:.0%} ahead<br>coin-in $%{customdata[0]:,.0f}–$%{customdata[1]:,.0f}"
                                             "<br>net/player $%{customdata[2]:,.0f} vs expected $%{customdata[3]:,.0f}<extra></extra>"))
        style(fig, f"Light players often win; heavy players almost never do ({pct(dec['share_ahead'].iloc[0])} vs {pct(dec['share_ahead'].iloc[-1])} ahead)",
              "Share of players who came out ahead, by coin-in decile (D1 = lightest)", height=340)
        fig.update_yaxes(tickformat=".0%", range=[0, max(dec["share_ahead"]) * 1.25])
        chart(fig)
        evidence("D-03")

    st.subheader("Guest segments")
    seg = d_players.segments(g)
    dim = st.radio("Compare by", ["age_band", "home_region", "opening_tier", "tier_end"], horizontal=True,
                   format_func=lambda d: {"age_band": "Age band", "home_region": "Home region", "opening_tier": "Tier at Jan 1", "tier_end": "Tier at the end"}[d])
    table(seg[seg["dimension"] == dim].drop(columns="dimension"),
          column_config={c: st.column_config.NumberColumn(format="dollar") for c in
                         ["coin_in_per_player_usd", "net_per_player_usd", "theo_per_player_usd", "comp_cost_per_player_usd"]}
          | {c: st.column_config.NumberColumn(format="percent") for c in ["hold", "share_ahead", "share_of_tracked_theo"]}
          | {c: st.column_config.NumberColumn(format="%.1f") for c in ["visits_per_player", "hours_per_player"]})

    st.subheader("A protective lens")
    prot = out("d7_protective")
    r = prot.iloc[0]
    st.markdown(f"The highest-loss 1% of tracked players ({int(r['players'])} people) carry **{pct(r['share_of_tracked_losses'])}** of "
                f"tracked losses and visit often (median {r['median_visits']:.0f} visits). Nothing in our plan targets them for more play. "
                f"Outside the budget we suggest:")
    for sgt in prot["suggestions"].iloc[0].split(" | "):
        st.markdown(f"- {sgt}")
    evidence("D-04")
