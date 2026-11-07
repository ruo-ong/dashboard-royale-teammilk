"""Loyalty members (Q4): what members wagered, received back and won or lost, and how concentrated the results are."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import date_range, evidence, money, out, pct, table, tracked_label
from tasks import d_players
from ui import BLUE, LIGHT_BLUE, card, detail, header, kpis, plot, section, summary, tile

DIMS = {"age_band": "Age group", "home_region": "Home region", "opening_tier": "Membership level on January 1", "tier_end": "Membership level at the end"}


@st.cache_data(show_spinner="Totalling member play for the selected months...")
def totals(months: tuple[str, ...]) -> pd.DataFrame:
    return d_players.player_totals(list(months))


def render() -> None:
    s, e = date_range()
    months = tuple(d_players.months_in(s, e))
    pt = out("player_totals") if len(months) == 6 else totals(months)
    header("Loyalty Members", "What members wagered, what they received back, and what they won or lost")
    tracked_label()

    with st.container(key="card_filters"):
        st.markdown('<div class="card-t">Choose a group of members</div><div class="card-s">Every figure on this page reflects the group selected here</div>',
                    unsafe_allow_html=True)
        cols = st.columns(4)
        picks = {dim: col.multiselect(label, sorted(pt[dim].dropna().unique()), key=f"p_{dim}") for col, (dim, label) in zip(cols, DIMS.items())}
    g = pt[pt["gamed"]]
    for dim, vals in picks.items():
        if vals:
            g = g[g[dim].isin(vals)]
    if g.empty:
        st.warning("No members match this selection.")
        return
    dec = d_players.luck_by_decile(g) if len(g) >= 10 else None
    theo = g["theo_usd"].to_numpy()
    top10 = np.sort(theo)[::-1][: max(1, int(0.1 * len(theo)))].sum() / theo.sum()

    summary(
        f"For the selected members and months ({', '.join(months)}), **{len(g):,} members** played on a loyalty card. Together they "
        f"wagered {money(g['tracked_coin_in_usd'].sum())} and received {money(g['tracked_payout_usd'].sum())} back in payouts, so as a "
        f"group they lost {money(-g['tracked_net_usd'].sum())}. The typical (median) member finished {money(g['tracked_net_usd'].median())}, "
        f"and **{pct(g['ahead'].mean(), 1)} of members finished ahead**.\n\n"
        + (f"Members who play less are more likely to finish ahead: {pct(dec['share_ahead'].iloc[0])} of the lightest players did so, "
           f"compared with {pct(dec['share_ahead'].iloc[-1])} of the heaviest. This is the expected effect of chance, which evens out "
           "over a larger amount of play. " if dec is not None else "")
        + f"Results are concentrated: the most active 10% of members account for {pct(top10)} of the expected win from member play.")
    kpis([tile("Amount wagered", money(g["tracked_coin_in_usd"].sum()), "by these members", "payments", "blue"),
          tile("Received back", money(g["tracked_payout_usd"].sum()), "in payouts", "redeem", "purple"),
          tile("Members' net result", money(g["tracked_net_usd"].sum()), "negative = the members lost", "account_balance_wallet", "orange"),
          tile("Members who finished ahead", pct(g["ahead"].mean(), 1), f"of {len(g):,} members", "emoji_events", "yellow"),
          tile("Typical member's result", money(g["tracked_net_usd"].median()), "median", "person", "teal")])

    a, b = st.columns(2)
    with a:
        with card("How members' results were distributed", "Number of members by net result. Dark blue: lost. Light blue: won."):
            edges = [-np.inf, -5000, -1000, -500, -250, -100, -50, -10, 0, 10, 50, 100, 250, 500, 1000, np.inf]
            labels = ["< −$5k", "−$5k to −$1k", "−$1k to −$500", "−$500 to −$250", "−$250 to −$100", "−$100 to −$50", "−$50 to −$10",
                      "−$10 to $0", "$0 to $10", "$10 to $50", "$50 to $100", "$100 to $250", "$250 to $500", "$500 to $1k", "> $1k"]
            counts = pd.cut(g["tracked_net_usd"], edges, labels=labels, right=False).value_counts().reindex(labels)
            fig = go.Figure(go.Bar(x=labels, y=counts.to_numpy(), marker={"color": [BLUE if l.startswith(("<", "−")) else LIGHT_BLUE for l in labels]},
                                   hovertemplate="%{x}: %{y:,} members<extra></extra>"))
            fig.update_xaxes(tickangle=-45)
            fig.update_layout(height=360, margin={"b": 110})
            plot(fig)
    with b:
        with card("Share of members who finished ahead, by amount played", "Members grouped into ten equal groups from the lightest (1) to the heaviest (10) players"):
            if dec is not None:
                fig = go.Figure(go.Bar(x=[str(d) for d in dec["decile"]], y=dec["share_ahead"], marker={"color": BLUE},
                                       text=[pct(v) for v in dec["share_ahead"]], textposition="outside",
                                       hovertemplate="Group %{x}: %{y:.0%} finished ahead<extra></extra>"))
                fig.update_yaxes(tickformat=".0%", range=[0, max(dec["share_ahead"]) * 1.25])
                fig.update_xaxes(title_text="Group (1 = lightest players)")
                fig.update_layout(height=360)
                plot(fig)

    a, b = st.columns(2)
    with a:
        with card("How concentrated play is", "Share of the total held by the lightest x% of members. A straight line would mean everyone played equally."):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line={"color": "#b5b5b5", "dash": "dot", "width": 1}, name="Equal play", hoverinfo="skip"))
            for name, values, colour in [("Expected win", theo, BLUE), ("Actual losses (members who lost)", (-g.loc[~g["ahead"], "tracked_net_usd"]).to_numpy(), LIGHT_BLUE)]:
                cum, _ = d_players._lorenz(values)
                x = np.linspace(0, 1, len(cum))
                idx = np.linspace(0, len(cum) - 1, 200).astype(int)
                fig.add_trace(go.Scatter(x=x[idx], y=cum[idx], mode="lines", name=name, line={"color": colour, "width": 2.5},
                                         hovertemplate="lightest %{x:.0%} of members: %{y:.0%} of the total<extra></extra>"))
            fig.update_xaxes(tickformat=".0%", title_text="Share of members, lightest first")
            fig.update_yaxes(tickformat=".0%")
            fig.update_layout(height=340, legend={"x": 0.02, "y": 0.98, "yanchor": "top"})
            plot(fig)
    with b:
        with card("Comparison of member groups", "Choose a characteristic to compare"):
            dim = st.radio("Compare by", list(DIMS), horizontal=True, format_func=DIMS.get, label_visibility="collapsed")
            seg = d_players.segments(g)
            seg = seg[seg["dimension"] == dim]
            table(seg[["segment", "players", "coin_in_per_player_usd", "net_per_player_usd", "share_ahead", "visits_per_player"]].rename(columns={
                "segment": "Group", "players": "Members", "coin_in_per_player_usd": "Wagered per member", "net_per_player_usd": "Net result per member",
                "share_ahead": "Finished ahead", "visits_per_player": "Visits per member"}),
                column_config={"Wagered per member": st.column_config.NumberColumn(format="dollar"),
                               "Net result per member": st.column_config.NumberColumn(format="dollar"),
                               "Finished ahead": st.column_config.NumberColumn(format="percent"),
                               "Visits per member": st.column_config.NumberColumn(format="%.1f")})

    section("Responsible play")
    prot = out("d7_protective")
    r = prot.iloc[0]
    st.markdown(f"The 1% of members with the largest losses ({int(r['players'])} people) account for {pct(r['share_of_tracked_losses'])} "
                f"of all losses on loyalty cards, and they visit often (a median of {r['median_visits']:.0f} visits in six months). Nothing in "
                "our recommendations is directed at encouraging these members to play more. Outside the budget, we suggest the following:")
    for sgt in prot["suggestions"].iloc[0].split(" | "):
        st.markdown(f"- {sgt}")

    with detail():
        st.markdown("**Terms.** *Tracked* play is play recorded on a loyalty card. *Expected win (theo)* is what the casino would expect "
                    "to keep from the wagers, based on each game's payback percentage. The concentration curves are Lorenz curves; "
                    "the Gini coefficient summarises them (0 = equal, 1 = fully concentrated).")
        evidence(["D-01", "D-02", "D-03", "D-04"])
        table(out("d3_concentration"))
        if dec is not None:
            table(dec)
        table(d_players.segments(g))
        table(prot.drop(columns="suggestions"))
