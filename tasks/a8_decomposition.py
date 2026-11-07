"""A8 - shortfall decomposition: why did this machine earn $X less than a typical machine?

Run:  python -m tasks.a8_decomposition [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a8_decomposition.parquet      machine x piece, in dollars (long format)
  -> outputs/charts/a8_decomposition.*     stacked bars for the manager's 10

House win = on-floor hours x availability x TPAH + luck. The "typical machine" is on the floor for the whole
window, with the median machine availability and the median machine TPAH. In this order the pieces add up
EXACTLY to (machine house win - typical house win):

  1. Short exposure       = (on-floor hours - full-window hours) x median availability x typical TPAH
  2. Downtime             = on-floor hours x (availability - median availability) x typical TPAH
  3. Location             = available hours x (bank peer TPAH - typical TPAH)
  4. Machine itself       = available hours x (machine TPAH - bank peer TPAH), split exactly into
     4a. play volume      = available hours x (coin-in/h - peer coin-in/h) x machine expected hold
     4b. game hold        = available hours x peer coin-in/h x (machine expected hold - peer implied hold)
  5. Luck                 = house win - theo

Bank peer TPAH and peer coin-in/h come from A5 (other machines in the same bank over the same days).
Peer implied hold = peer TPAH / peer coin-in per hour. 4a + 4b equals the plan's single "machine itself" piece.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from royale.charts import COLORS, save, style
from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.util import safe_ratio
from tasks import a5_location
from tasks.a1_manager_list import manager_ten

PIECES = [  # (column, label, colour) in fixed order
    ("short_exposure_usd", "Short exposure", COLORS["series_1"]),
    ("downtime_usd", "Downtime", COLORS["series_2"]),
    ("location_usd", "Location", COLORS["series_3"]),
    ("machine_volume_usd", "Machine: play volume", COLORS["series_4"]),
    ("machine_hold_usd", "Machine: game hold", COLORS["series_5"]),
    ("luck_usd", "Luck", COLORS["series_6"]),
]
CENT = 0.01


def compute(base: pd.DataFrame, start=None, end=None, manager_ids: list[str] | None = None,
            location: pd.DataFrame | None = None) -> pd.DataFrame:
    """Wide table: one row per machine, one column per piece, plus the reference values used."""
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    if location is None:
        location = a5_location.compute(base, manager_ids)[0]
    start = start or base["gaming_date"].min()
    end = end or base["gaming_date"].max()
    full_window_hours = load("calendar_day", start=start, end=end)["scheduled_seconds"].sum() / 3600.0

    m = summarize(base, "machine_id")
    m = m.merge(location[["machine_id", "zone_id", "bank_id", "theme", "bank_peer_tpah", "bank_peer_coin_in_per_hour"]],
                on="machine_id", how="left")
    median_availability = m["availability"].median()
    typical_tpah = m["tpah"].median()

    peer_tpah = m["bank_peer_tpah"].fillna(typical_tpah)
    peer_cph = m["bank_peer_coin_in_per_hour"].fillna(m["coin_in_per_avail_hour"])
    peer_hold = safe_ratio(peer_tpah, peer_cph)
    hold = m["expected_hold"].fillna(0.0)
    cph = m["coin_in_per_avail_hour"].fillna(0.0)

    out = m[["machine_id", "zone_id", "bank_id", "theme", "on_floor_hours", "available_hours", "availability",
             "tpah", "house_win_usd", "theo_usd"]].copy()
    out["full_window_hours"] = full_window_hours
    out["median_availability"] = median_availability
    out["typical_tpah"] = typical_tpah
    out["bank_peer_tpah"] = peer_tpah
    out["typical_win_usd"] = full_window_hours * median_availability * typical_tpah
    out["gap_usd"] = out["house_win_usd"] - out["typical_win_usd"]

    out["short_exposure_usd"] = (m["on_floor_hours"] - full_window_hours) * median_availability * typical_tpah
    out["downtime_usd"] = m["on_floor_hours"] * (m["availability"] - median_availability) * typical_tpah
    out["location_usd"] = m["available_hours"] * (peer_tpah - typical_tpah)
    out["machine_volume_usd"] = m["available_hours"] * (cph - peer_cph) * hold
    out["machine_hold_usd"] = m["available_hours"] * peer_cph * (hold - peer_hold)
    out["machine_itself_usd"] = out["machine_volume_usd"] + out["machine_hold_usd"]
    out["luck_usd"] = m["luck_residual_usd"]

    pieces = [col for col, _, _ in PIECES]
    out["pieces_sum_usd"] = out[pieces].sum(axis=1)
    out["largest_negative_piece"] = out[pieces].idxmin(axis=1).map({c: label for c, label, _ in PIECES})
    out.loc[out[pieces].min(axis=1) >= 0, "largest_negative_piece"] = ""
    out["in_manager_10"] = out["machine_id"].isin(manager_ids)
    return out.sort_values("gap_usd").reset_index(drop=True)


def to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """machine x piece, the contract format for A9 and the dashboard."""
    keep = ["machine_id", "zone_id", "bank_id", "house_win_usd", "typical_win_usd", "gap_usd", "in_manager_10"]
    long = wide.melt(id_vars=keep, value_vars=[c for c, _, _ in PIECES], var_name="piece_column", value_name="usd")
    order = {c: i for i, (c, _, _) in enumerate(PIECES, start=1)}
    long["piece_order"] = long["piece_column"].map(order)
    long["piece"] = long["piece_column"].map({c: label for c, label, _ in PIECES})
    return long.drop(columns="piece_column").sort_values(["gap_usd", "machine_id", "piece_order"]).reset_index(drop=True)


def figure(wide: pd.DataFrame, manager_ids: list[str]) -> go.Figure:
    ten = wide.set_index("machine_id").loc[list(reversed(manager_ids))].reset_index()  # rank 1 at the top
    totals = {label: ten[col].sum() for col, label, _ in PIECES}
    worst_label = min(totals, key=totals.get)
    fig = go.Figure()
    for col, label, colour in PIECES:
        fig.add_trace(go.Bar(y=ten["machine_id"], x=ten[col], orientation="h", name=label,
                             marker={"color": colour, "line": {"color": COLORS["surface"], "width": 2}},
                             customdata=np.stack([ten["zone_id"], ten["theme"]], axis=1),
                             hovertemplate=f"<b>%{{y}}</b> · %{{customdata[0]}} · %{{customdata[1]}}<br>{label}: "
                                           "%{x:$,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(y=ten["machine_id"], x=ten["gap_usd"], mode="markers", name="Total gap vs typical",
                             marker={"symbol": "diamond", "size": 11, "color": COLORS["text"],
                                     "line": {"color": COLORS["surface"], "width": 2}},
                             hovertemplate="<b>%{y}</b><br>house win − typical machine: %{x:$,.0f}<extra></extra>"))
    # Total as a direct label just past the left end of each bar, so it never sits on a segment.
    left_end = ten[[c for c, _, _ in PIECES]].clip(upper=0).sum(axis=1)
    fig.add_trace(go.Scatter(y=ten["machine_id"], x=left_end, mode="text", showlegend=False, hoverinfo="skip",
                             text=[f"{v / 1000:+,.0f}k  " for v in ten["gap_usd"]], textposition="middle left",
                             textfont={"size": 11, "color": COLORS["text"]}))
    fig.add_vline(x=0, line={"color": COLORS["text_secondary"], "width": 1})
    r = wide.iloc[0]
    style(fig, f"{worst_label} is the biggest reason the manager's 10 earned less: "
               f"${-totals[worst_label] / 1000:,.0f}k of their ${-ten['gap_usd'].sum() / 1000:,.0f}k combined shortfall",
          f"House win minus a typical machine (on the floor all {r['full_window_hours'] / 24:,.0f} days, availability "
          f"{r['median_availability']:.1%}, TPAH ${r['typical_tpah']:.2f}/h). Pieces add up exactly to the gap (◆).",
          height=560)
    fig.update_layout(barmode="relative", bargap=0.35, legend={"y": -0.12, "yanchor": "top", "x": 0, "xanchor": "left"})
    lo = left_end.min()
    fig.update_xaxes(title_text="Dollars vs a typical machine", tickformat="$,.0f", range=[lo * 1.12, None])
    fig.update_yaxes(showgrid=False)
    return fig


def main() -> None:
    args = window_args("A8 shortfall decomposition")
    base = load_base(args.start, args.end)
    ids = manager_ten()
    wide = compute(base, args.start, args.end, ids)
    worst = (wide["pieces_sum_usd"] - wide["gap_usd"]).abs().max()
    print(f"{'PASS' if worst <= CENT else 'FAIL'}: pieces add up to the gap for all {len(wide)} machines "
          f"(max error ${worst:.6f})")
    if worst > CENT:
        raise SystemExit("Decomposition does not add up; nothing written.")
    write_output("a8_decomposition", to_long(wide))
    save(figure(wide, ids), "a8_decomposition")

    show = wide.set_index("machine_id").loc[ids]
    cols = ["gap_usd"] + [c for c, _, _ in PIECES]
    print("\nThe manager's 10, dollars vs a typical machine:")
    print((show[cols] / 1000).round(1).rename(columns=lambda c: c.replace("_usd", "") + "_k").to_string())
    print("\nSum over the 10 ($k):")
    print((show[cols].sum() / 1000).round(1).to_string())
    print("\nWrote outputs/a8_decomposition.parquet (machine x piece) and outputs/charts/a8_decomposition")


if __name__ == "__main__":
    main()
