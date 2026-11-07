"""A2 - exposure test: does each machine still look weak once we measure per AVAILABLE HOUR of play value?

Run:  python -m tasks.a2_exposure [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a2_exposure.parquet      one row per machine
  -> outputs/charts/a2_rank_shift.*   the manager's 10: house-win rank vs TPAH rank

Rank 1 = lowest. TPAH (theo per available hour) removes both luck (theo, not house win) and exposure
(per available hour, so short stays and downtime do not count against the machine). It does NOT remove
location: a machine in a quiet bank still has a low TPAH. That is A5's job.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from royale.charts import COLORS, save, style
from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from tasks.a1_manager_list import manager_ten

LOW_EVIDENCE_DAYS = 60       # fewer on-floor days than this -> too little data for a verdict (plan A2)
BOTTOM = 10
DOWNTIME_GAP = 0.01          # availability this far below the floor's counts as a downtime reason (note only)
UNLUCKY_Z = -2.0             # luck z at or below this counts as a luck reason (note only; A3 owns luck)

ATTRS = ["zone_id", "bank_id", "config_id", "theme", "manufacturer", "lease_class", "install_date", "retire_date"]


def _window_days(start, end, base: pd.DataFrame) -> int:
    start = start or base["gaming_date"].min()
    end = end or base["gaming_date"].max()
    return len(load("calendar_day", start=start, end=end))


def compute(base: pd.DataFrame, start=None, end=None, manager_ids: list[str] | None = None) -> pd.DataFrame:
    """Per-machine exposure metrics and rank movement for an already-windowed machine_day_base."""
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    window_days = _window_days(start, end, base)
    start_ts = pd.Timestamp(start or base["gaming_date"].min())
    end_ts = pd.Timestamp(end or base["gaming_date"].max())

    m = summarize(base, "machine_id")
    ordered = base.sort_values("gaming_date").groupby("machine_id")
    attrs = ordered[ATTRS].last()
    attrs["first_day"] = ordered["gaming_date"].min()
    attrs["last_day"] = ordered["gaming_date"].max()
    m = m.merge(attrs, on="machine_id")

    m["window_days"] = window_days
    m["partial_window"] = m["days_on_floor"] < window_days
    m["low_evidence"] = m["days_on_floor"] < LOW_EVIDENCE_DAYS
    m["rank_house_win"] = m["house_win_usd"].rank(method="first").astype(int)
    m["rank_tpah"] = m["tpah"].rank(method="first").astype(int)
    m["rank_change"] = m["rank_tpah"] - m["rank_house_win"]
    m["in_manager_10"] = m["machine_id"].isin(manager_ids)

    floor = summarize(base).iloc[0]
    median_tpah = m["tpah"].median()

    def note(row) -> str:
        if not row["in_manager_10"]:
            return ""
        verdict = "stays in" if row["rank_tpah"] <= BOTTOM else "leaves"
        reasons = []
        if row["partial_window"]:
            if pd.notna(row["install_date"]) and pd.Timestamp(row["install_date"]) > start_ts:
                when = f"installed {pd.Timestamp(row['install_date']):%b %-d}"
            elif pd.notna(row["retire_date"]) and pd.Timestamp(row["retire_date"]) <= end_ts:
                when = f"retired {pd.Timestamp(row['retire_date']):%b %-d}"
            else:
                when = "partial window"
            reasons.append(f"short exposure: on the floor {row['days_on_floor']} of {window_days} days ({when})")
        if row["availability"] < floor["availability"] - DOWNTIME_GAP:
            reasons.append(f"downtime: available {row['availability']:.1%} vs floor {floor['availability']:.1%}")
        if row["luck_z"] <= UNLUCKY_Z:
            reasons.append(f"bad luck: house win ${-row['luck_residual_usd']:,.0f} below theo (luck z {row['luck_z']:.1f})")
        if row["tpah"] < median_tpah:
            reasons.append(f"low play value: TPAH ${row['tpah']:.2f} vs floor median ${median_tpah:.2f}")
        else:
            reasons.append(f"normal play value: TPAH ${row['tpah']:.2f} vs floor median ${median_tpah:.2f}")
        return (f"House-win rank {row['rank_house_win']} -> TPAH rank {row['rank_tpah']} "
                f"({verdict} the bottom {BOTTOM}). " + "; ".join(reasons) + ".")

    m["rank_note"] = m.apply(note, axis=1)
    return m.sort_values("rank_house_win").reset_index(drop=True)


def rank_shift_figure(exposure: pd.DataFrame) -> go.Figure:
    """Dumbbell: for each of the manager's 10, house-win rank (grey) -> TPAH rank (blue)."""
    ten = exposure[exposure["in_manager_10"]].sort_values("rank_house_win", ascending=False)
    n_machines = len(exposure)
    stays = int((ten["rank_tpah"] <= BOTTOM).sum())
    fig = go.Figure()
    fig.add_vrect(x0=0.5, x1=BOTTOM + 0.5, fillcolor=COLORS["grid"], opacity=0.6, line_width=0, layer="below")
    fig.add_annotation(x=BOTTOM + 0.5, y=1.0, yref="paper", text=f"bottom {BOTTOM}", showarrow=False,
                       xanchor="left", yanchor="bottom", font={"color": COLORS["text_secondary"], "size": 12})
    for _, row in ten.iterrows():
        fig.add_trace(go.Scatter(x=[row["rank_house_win"], row["rank_tpah"]], y=[row["machine_id"]] * 2,
                                 mode="lines", line={"color": COLORS["neutral"], "width": 2},
                                 hoverinfo="skip", showlegend=False))
    hover = ("<b>%{y}</b><br>%{customdata[0]}<br>house-win rank %{customdata[1]} -> TPAH rank %{customdata[2]}"
             "<br>TPAH $%{customdata[3]:.2f}/h · %{customdata[4]} days on floor<extra></extra>")
    custom = ten[["zone_id", "rank_house_win", "rank_tpah", "tpah", "days_on_floor"]].to_numpy()
    fig.add_trace(go.Scatter(x=ten["rank_house_win"], y=ten["machine_id"], mode="markers", name="Rank by house win",
                             marker={"size": 10, "color": COLORS["neutral"], "line": {"color": COLORS["surface"], "width": 2}},
                             customdata=custom, hovertemplate=hover))
    fig.add_trace(go.Scatter(x=ten["rank_tpah"], y=ten["machine_id"], mode="markers", name="Rank by TPAH",
                             marker={"size": 10, "color": COLORS["series_1"], "line": {"color": COLORS["surface"], "width": 2}},
                             customdata=custom, hovertemplate=hover))
    # Direct label to the right of whichever dot is further right, so it never sits on a marker.
    fig.add_trace(go.Scatter(x=ten[["rank_house_win", "rank_tpah"]].max(axis=1) + 3, y=ten["machine_id"],
                             mode="text", text="TPAH rank " + ten["rank_tpah"].astype(str), textposition="middle right",
                             textfont={"color": COLORS["text_secondary"], "size": 11}, hoverinfo="skip", showlegend=False))
    style(fig, f"{stays} of the manager's 10 stay in the bottom {BOTTOM} when ranked by play value per available hour",
          f"Rank among {n_machines} machines, 1 = lowest. Grey = total house win (the manager's ranking); "
          f"blue = theo per available hour (TPAH)", height=460)
    fig.update_xaxes(title_text="Rank (1 = lowest)", range=[0, n_machines + 12], showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def main() -> None:
    args = window_args("A2 exposure test")
    exposure = compute(load_base(args.start, args.end), args.start, args.end)
    write_output("a2_exposure", exposure)
    save(rank_shift_figure(exposure), "a2_rank_shift")
    ten = exposure[exposure["in_manager_10"]]
    print("\nThe manager's 10:")
    for _, row in ten.iterrows():
        print(f"  {row['machine_id']} ({row['zone_id']}): {row['rank_note']}")
    partial = exposure[exposure["partial_window"]]
    low = exposure[exposure["low_evidence"]]
    print(f"\nPartial-window machines ({len(partial)}): {', '.join(partial['machine_id'])}")
    print(f"Low-evidence machines, < {LOW_EVIDENCE_DAYS} days ({len(low)}): {', '.join(low['machine_id'])}")
    print(f"Wrote outputs/a2_exposure.parquet ({len(exposure)} machines) and outputs/charts/a2_rank_shift")


if __name__ == "__main__":
    main()
