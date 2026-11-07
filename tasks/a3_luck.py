"""A3 - luck test: is a machine's low house win just a normal swing of chance?

Run:  python -m tasks.a3_luck [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a3_luck.parquet          one row per machine
  -> outputs/a3_luck_monthly.parquet  one row per machine x month
  -> outputs/charts/a3_luck_z_hist.*  luck z for every machine, the manager's 10 marked

Luck residual = house win - theo (negative = the house was unlucky).
Luck SD = sqrt(sum over days of sum_bet^2 x payout variance): the size of a normal swing for this much play.
Luck z = residual / SD. |z| < 2 is ordinary luck. Sanity check: across all machines z should look like a
bell curve centred near 0 with ~5% beyond +-2. If it does not, the variance units are wrong.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from royale.charts import COLORS, save, style
from royale.cli import window_args
from royale.data import load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.util import safe_ratio
from tasks.a1_manager_list import manager_ten

ORDINARY_Z = 2.0

KEEP = ["machine_id", "days_on_floor", "coin_in_usd", "theo_usd", "house_win_usd", "luck_residual_usd",
        "luck_sd_usd", "luck_z", "observed_hold", "expected_hold"]


def monthly(base: pd.DataFrame) -> pd.DataFrame:
    """Luck per machine x month (ratio of sums inside each month)."""
    out = summarize(base, ["machine_id", "month"])
    return out[["machine_id", "month", "days_on_floor", "theo_usd", "house_win_usd", "luck_residual_usd",
                "luck_sd_usd", "luck_z"]]


def compute(base: pd.DataFrame, manager_ids: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-machine luck table, per-machine-month luck table) for an already-windowed base."""
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    luck = summarize(base, "machine_id")[KEEP].copy()

    # Biggest single day in the direction of the total: one jackpot, or a steady drift?
    daily = base[["machine_id", "gaming_date", "luck_residual_usd", "luck_var_usd2"]].merge(
        luck[["machine_id", "luck_residual_usd"]].rename(columns={"luck_residual_usd": "total"}), on="machine_id")
    daily["signed"] = daily["luck_residual_usd"] * np.sign(daily["total"])
    biggest = daily.loc[daily.groupby("machine_id")["signed"].idxmax(),
                        ["machine_id", "gaming_date", "luck_residual_usd", "luck_var_usd2"]]
    biggest.columns = ["machine_id", "biggest_day", "biggest_day_residual_usd", "_biggest_var"]
    luck = luck.merge(biggest, on="machine_id")
    luck["biggest_day_share"] = safe_ratio(luck["biggest_day_residual_usd"], luck["luck_residual_usd"])
    remaining_var = (luck["luck_sd_usd"] ** 2 - luck["_biggest_var"]).clip(lower=0)
    luck["luck_z_ex_biggest_day"] = safe_ratio(
        luck["luck_residual_usd"] - luck["biggest_day_residual_usd"], np.sqrt(remaining_var))
    luck = luck.drop(columns="_biggest_var")

    months = monthly(base)
    month_stats = months.groupby("machine_id").agg(
        months_on_floor=("month", "nunique"),
        months_negative=("luck_residual_usd", lambda r: int((r < 0).sum())),
        worst_month_z=("luck_z", "min"))
    luck = luck.merge(month_stats, on="machine_id")

    luck["luck_band"] = np.select([luck["luck_z"] <= -ORDINARY_Z, luck["luck_z"] >= ORDINARY_Z],
                                  ["unlucky", "lucky"], "ordinary")
    luck["in_manager_10"] = luck["machine_id"].isin(manager_ids)
    return luck.sort_values("luck_z").reset_index(drop=True), months


def histogram_figure(luck: pd.DataFrame) -> go.Figure:
    """Top: luck z for every machine. Bottom: where each of the manager's 10 falls."""
    ten = luck[luck["in_manager_10"]].sort_values("luck_z", ascending=False)
    n_unlucky = int((ten["luck_z"] <= -ORDINARY_Z).sum())
    share_beyond = (luck["luck_z"].abs() > ORDINARY_Z).mean()
    lo = np.floor(min(luck["luck_z"].min(), -3)) - 0.5
    hi = np.ceil(max(luck["luck_z"].max(), 3)) + 0.5

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.55, 0.45], vertical_spacing=0.06)
    fig.add_trace(go.Histogram(x=luck["luck_z"], xbins={"start": lo, "end": hi, "size": 0.5},
                               marker={"color": COLORS["series_1"], "line": {"color": COLORS["surface"], "width": 2}},
                               name=f"All {len(luck)} machines",
                               hovertemplate="luck z %{x}<br>%{y} machines<extra></extra>"), row=1, col=1)
    labels = [f"{z:+.1f}" for z in ten["luck_z"]]
    fig.add_trace(go.Scatter(x=ten["luck_z"], y=ten["machine_id"], mode="markers+text", name="The manager's 10",
                             text=labels, textposition="middle right", textfont={"color": COLORS["text_secondary"], "size": 11},
                             marker={"size": 10, "color": COLORS["series_2"], "line": {"color": COLORS["surface"], "width": 2}},
                             customdata=ten[["luck_residual_usd", "luck_sd_usd", "months_negative", "months_on_floor"]].to_numpy(),
                             hovertemplate=("<b>%{y}</b><br>luck z %{x:.2f}<br>house win − theo $%{customdata[0]:,.0f}"
                                            "<br>normal swing ±$%{customdata[1]:,.0f}"
                                            "<br>%{customdata[2]} of %{customdata[3]} months unlucky<extra></extra>")),
                  row=2, col=1)
    # Shapes go in after the traces: Plotly drops shapes on subplots that are still empty.
    for row in (1, 2):
        fig.add_vrect(x0=-ORDINARY_Z, x1=ORDINARY_Z, fillcolor=COLORS["grid"], opacity=0.6, line_width=0,
                      layer="below", row=row, col=1)
    fig.add_annotation(x=0, y=1.0, xref="x", yref="y domain", text=f"ordinary luck (|z| < {ORDINARY_Z:g})",
                       showarrow=False, yanchor="bottom", font={"color": COLORS["text_secondary"], "size": 12})
    style(fig, f"Only {n_unlucky} of the manager's 10 were unusually unlucky; the rest is ordinary variation",
          f"Luck z = (house win − theo) ÷ the normal swing for that much play, per machine. "
          f"{share_beyond:.1%} of all machines fall beyond ±{ORDINARY_Z:g} (≈5% expected by chance).", height=620)
    fig.update_xaxes(range=[lo, hi], showgrid=False)
    fig.update_xaxes(title_text="Luck z (negative = house unlucky)", row=2, col=1)
    fig.update_yaxes(title_text="Machines", row=1, col=1)
    fig.update_yaxes(showgrid=False, row=2, col=1)
    return fig


def main() -> None:
    args = window_args("A3 luck test")
    luck, months = compute(load_base(args.start, args.end))
    write_output("a3_luck", luck)
    write_output("a3_luck_monthly", months)
    save(histogram_figure(luck), "a3_luck_z_hist")

    z = luck["luck_z"]
    print(f"\nSanity check over {len(luck)} machines: mean z {z.mean():+.2f}, sd {z.std():.2f}, "
          f"{(z.abs() > ORDINARY_Z).mean():.1%} beyond ±{ORDINARY_Z:g} (expect ≈5%)")
    print("\nThe manager's 10:")
    cols = ["machine_id", "luck_residual_usd", "luck_sd_usd", "luck_z", "biggest_day", "biggest_day_share",
            "luck_z_ex_biggest_day", "months_negative", "months_on_floor", "luck_band"]
    show = luck[luck["in_manager_10"]][cols].copy()
    show["biggest_day"] = show["biggest_day"].dt.strftime("%b %d")
    print(show.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"\nWrote outputs/a3_luck.parquet, outputs/a3_luck_monthly.parquet and outputs/charts/a3_luck_z_hist")


if __name__ == "__main__":
    main()
