"""Underperforming machines: every machine on the floor against what its location, game and manufacturer should earn."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import date_range, evidence, is_full_window, money, out, pct, table, zone_bank_filter
from royale.data import load_base
from tasks import a12_floor_screen
from ui import BLUE, LIGHT_BLUE, card, detail, header, html_table, key_points, kpis, plot, section, tile

GREY = "#d5dbee"
STATUS_COLOR = {"Underperforms": BLUE, "Watch": LIGHT_BLUE, "In line": GREY}


@st.cache_data(show_spinner="Comparing every machine with its expectation for this period...")
def screen_for(start, end) -> pd.DataFrame:
    if (start, end) == (pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-06-30").date()):
        return out("a12_floor_screen")
    return a12_floor_screen.compute(load_base(start, end))


def distribution(s: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for status in ["In line", "Watch", "Underperforms"]:
        part = s[s["status"] == status]
        fig.add_trace(go.Histogram(x=part["ratio_whole"], name=status, marker={"color": STATUS_COLOR[status]},
                                   xbins={"start": 0.80, "end": 1.20, "size": 0.01},
                                   hovertemplate="%{x:.0%} of expected: %{y} machines<extra>" + status + "</extra>"))
    for x, label in [(a12_floor_screen.UNDER, "0.90"), (1.0, "as expected")]:
        fig.add_vline(x=x, line={"color": "#a3aed0", "width": 1, "dash": "dot"})
        fig.add_annotation(x=x, y=0.97, yref="paper", text=label, showarrow=False, yanchor="top", xanchor="left", xshift=4,
                           font={"size": 11, "color": "#707eae"})
    fig.update_layout(barmode="stack", height=320, bargap=0.08)
    fig.update_xaxes(tickformat=".0%", title_text="Expected win per working hour, compared with its expectation")
    fig.update_yaxes(title_text="Machines")
    return fig


def consistency(s: pd.DataFrame) -> go.Figure:
    d = s[s["status"].isin(["Underperforms", "Watch"])].sort_values("ratio_whole", ascending=False)
    fig = go.Figure()
    for _, r in d.iterrows():
        fig.add_trace(go.Scatter(x=[min(r["ratio_first_half"], r["ratio_second_half"]), max(r["ratio_first_half"], r["ratio_second_half"])],
                                 y=[r["machine_id"]] * 2, mode="lines", line={"color": "#e2e6f5", "width": 6}, hoverinfo="skip", showlegend=False))
    for col, name, sym, size in [("ratio_first_half", "First half", "circle-open", 9), ("ratio_second_half", "Second half", "diamond-open", 9)]:
        fig.add_trace(go.Scatter(x=d[col], y=d["machine_id"], mode="markers", name=name, marker={"symbol": sym, "size": size, "color": "#707eae"},
                                 hovertemplate="%{y}: %{x:.0%} of expected<extra>" + name + "</extra>"))
    fig.add_trace(go.Scatter(x=d["ratio_whole"], y=d["machine_id"], mode="markers", name="Whole period",
                             marker={"size": 12, "color": [STATUS_COLOR[x] for x in d["status"]]},
                             customdata=d[["theme", "zone_name"]].to_numpy(),
                             hovertemplate="%{y}, %{customdata[0]}, %{customdata[1]}: %{x:.0%} of expected<extra></extra>"))
    fig.add_vline(x=a12_floor_screen.UNDER, line={"color": "#a3aed0", "width": 1, "dash": "dot"})
    fig.update_xaxes(tickformat=".0%", title_text="Compared with expectation")
    fig.update_yaxes(showgrid=False)
    fig.update_layout(height=max(260, 26 * len(d) + 90))
    return fig


def by_zone(s: pd.DataFrame) -> go.Figure:
    z = s[s["status"] != "Too little data"].groupby("zone_name").agg(
        machines=("machine_id", "size"), below=("status", lambda x: x.isin(["Underperforms", "Watch"]).sum())).reset_index()
    z["share"] = z["below"] / z["machines"]
    z = z.sort_values("share")
    fig = go.Figure(go.Bar(x=z["share"], y=z["zone_name"], orientation="h", marker={"color": [BLUE if v == z["share"].max() else LIGHT_BLUE for v in z["share"]]},
                           text=[f"{int(b)} of {int(m)}" for b, m in zip(z["below"], z["machines"])], textposition="outside",
                           hovertemplate="%{y}: %{x:.0%} of machines below expectation<extra></extra>"))
    fig.update_xaxes(tickformat=".0%", range=[0, max(0.1, z["share"].max() * 1.35)])
    fig.update_yaxes(showgrid=False)
    fig.update_layout(height=300)
    return fig


def render() -> None:
    start, end = date_range()
    full = screen_for(start, end)
    s = zone_bank_filter(full)
    elig = s[s["status"] != "Too little data"]
    under = s[s["status"] == "Underperforms"]
    watch = s[s["status"] == "Watch"]
    header("Underperforming Machines", "Every machine on the floor, compared with what its location, game and manufacturer should earn")
    kpis([tile("Machines assessed", f"{len(elig)}", "60 or more days on the floor", "fact_check", "indigo"),
          tile("Underperform consistently", f"{len(under)}", "more than 10% below, both halves", "trending_down", "orange"),
          tile("Watch list", f"{len(watch)}", "slightly below, not consistent", "visibility", "yellow"),
          tile("Shortfall of underperformers", money(under["shortfall_usd"].sum()), "expected win, this period", "money_off", "red")])
    lo, hi = (elig["ratio_whole"].quantile([0.05, 0.95]) if len(elig) else (float("nan"), float("nan")))
    fit = under[under["game_location_fit_issue"]]
    games_txt = ", ".join(sorted(set(fit["theme"])))
    points = ["Each machine is compared with what a machine with the same **location, game and manufacturer** would be expected to "
              "earn. Luck and time out of service are removed.",
              f"Once those are allowed for, machines are very similar: 90% are between **{pct(lo - 1, 0, True)}** and **{pct(hi - 1, 0, True)}** of expectation."]
    if len(under):
        points.append(f"**{len(under)}** machine{'s' if len(under) > 1 else ''} earn{'' if len(under) > 1 else 's'} consistently more than 10% less "
                      f"than expected, in both halves of the period: **{', '.join(under['machine_id'])}**.")
    else:
        points.append("No machine earns consistently more than 10% less than expected in both halves of the period.")
    if len(fit):
        points.append(f"Their game ({games_txt}) also runs below expectation on the other machines in the same area, while it meets expectation "
                      "elsewhere. The remedy is **where the game stands**, not replacing the machines.")
    if len(watch):
        top_zone = watch["zone_name"].value_counts()
        points.append(f"**{len(watch)}** machines are slightly below expectation but not consistently; {int(top_zone.iloc[0])} of them are in the "
                      f"**{top_zone.index[0]}**. Review them again next quarter.")
    key_points(points, more=(
        "The comparison uses the machine estimator (location, game and manufacturer), fitted on the period shown, to give each machine "
        "an expected win per working hour. Expected win removes luck; measuring per working hour removes time out of service and the "
        "date a machine was installed or removed. A machine is said to underperform only if it is more than 10% below its expectation "
        "over the whole period and in each half, so that one bad stretch is not enough. Machines more than 7% below over the whole "
        "period, but not consistently, are placed on a watch list. Machines with fewer than 60 days on the floor are not judged."
        + ("" if is_full_window() else "\n\n*Recalculated for the period selected in the sidebar.*")))

    with card("How every machine compares with its expectation", "Number of machines by expected win per working hour, as a share of what "
                                                                  "a machine with the same location, game and manufacturer should earn"):
        plot(distribution(elig), legend_top=True)
    a, b = st.columns([3, 2])
    with a:
        with card("Machines below expectation, and how consistent they are",
                  "Large dot: whole period. Open markers: each half. Underperformers are below 90% in all three."):
            if len(under) + len(watch):
                plot(consistency(s), legend_top=True)
            else:
                st.markdown("No machine is below expectation in this selection.")
    with b:
        with card("Where they are", "Share of machines in each area that are on the watch list or underperform"):
            plot(by_zone(s))

    section("Machines to act on or review")
    show = pd.concat([under, watch])
    if len(show):
        t = show.assign(vs=lambda d: d["ratio_whole"].map(lambda x: f"{x - 1:+.0%}"), short=lambda d: d["shortfall_usd"].map(lambda x: money(x)))
        html_table(t[["machine_id", "status", "zone_name", "theme", "vs", "short", "advice"]].rename(columns={
            "machine_id": "Machine", "status": "Status", "zone_name": "Area", "theme": "Game", "vs": "Vs expected",
            "short": "Shortfall", "advice": "Recommendation"}), badge_col="Status")
    else:
        st.markdown("No machine is below expectation in this selection.")

    with detail():
        st.markdown(f"**Thresholds.** Underperforms: below {a12_floor_screen.UNDER:.2f} of expected over the period and in each half. "
                    f"Watch: below {a12_floor_screen.WATCH:.2f} over the period. Game-location fit: the same game's other machines in the "
                    f"same zone average below {a12_floor_screen.FIT_MIN:.2f}. Spread (standard deviation) of the ratio: "
                    f"{elig['ratio_whole'].std():.3f}.")
        table(s, column_config={c: st.column_config.NumberColumn(format="%.3f") for c in
                                ["ratio_whole", "ratio_first_half", "ratio_second_half", "z", "same_game_same_zone_ratio"]}
              | {c: st.column_config.NumberColumn(format="dollar") for c in ["tpah", "expected_tpah", "shortfall_usd"]})
        evidence(["A12-01", "M6-01"])
