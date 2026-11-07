"""The team's shared metric definitions (docs/METRICS.md), implemented once as ratios of sums.

    from royale.outputs import read_output
    from royale.data import window
    from royale.metrics import summarize

    base = window(read_output("machine_day_base"), "2025-01-01", "2025-06-30")
    by_machine = summarize(base, "machine_id")             # one row per machine
    by_bank    = summarize(base, ["zone_id", "bank_id"])   # one row per bank
    floor      = summarize(base)                           # one row for the whole floor

Filter the date range (and anything else) BEFORE calling summarize. Every ratio is computed from
sums over the rows you pass, so it is correct for any period, grouping or subset.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.util import safe_ratio

# Columns of machine_day_base that are summed before any ratio is taken.
SUM_COLUMNS = [
    "on_floor_hours", "available_hours", "down_hours", "occupied_hours",
    "paid_spins", "payout_positive_spins",
    "coin_in_usd", "payout_usd", "house_win_usd", "theo_usd", "luck_residual_usd",
    "luck_var_usd2", "expected_hits", "hit_var",
    "carded_coin_in_usd", "carded_theo_usd",
    "supplied_costs_usd", "contribution_usd", "faults_opened",
]


def summarize(base: pd.DataFrame, by: str | list[str] | None = None) -> pd.DataFrame:
    """Aggregate machine_day_base rows into the shared metrics.

    Returns the summed columns plus:
      days_on_floor, machines, availability, occupancy, tpah (theo per available hour),
      coin_in_per_avail_hour, house_win_per_avail_hour, observed_hold, expected_hold,
      luck_sd_usd, luck_z, hit_rate_z, carded_share, contribution_per_avail_hour.
    """
    by = [by] if isinstance(by, str) else list(by or [])
    present = [c for c in SUM_COLUMNS if c in base.columns]
    if by:
        grouped = base.groupby(by, observed=True, dropna=False)
        out = grouped[present].sum()
        out["days_on_floor"] = grouped.size()
        out["machines"] = grouped["machine_id"].nunique()
        out = out.reset_index()
    else:
        out = base[present].sum().to_frame().T
        out["days_on_floor"] = len(base)
        out["machines"] = base["machine_id"].nunique()

    out["availability"] = safe_ratio(out["available_hours"], out["on_floor_hours"])
    out["occupancy"] = safe_ratio(out["occupied_hours"], out["available_hours"])
    out["tpah"] = safe_ratio(out["theo_usd"], out["available_hours"])
    out["coin_in_per_avail_hour"] = safe_ratio(out["coin_in_usd"], out["available_hours"])
    out["house_win_per_avail_hour"] = safe_ratio(out["house_win_usd"], out["available_hours"])
    out["observed_hold"] = safe_ratio(out["house_win_usd"], out["coin_in_usd"])
    out["expected_hold"] = safe_ratio(out["theo_usd"], out["coin_in_usd"])
    # Luck: variances add across days, standard deviations do not. sqrt AFTER summing.
    out["luck_sd_usd"] = np.sqrt(out["luck_var_usd2"].astype("float64"))
    out["luck_z"] = safe_ratio(out["luck_residual_usd"], out["luck_sd_usd"])
    out["hit_rate_z"] = safe_ratio(
        out["payout_positive_spins"] - out["expected_hits"], np.sqrt(out["hit_var"].astype("float64"))
    )
    if "carded_coin_in_usd" in out:
        out["carded_share"] = safe_ratio(out["carded_coin_in_usd"], out["coin_in_usd"])
    if "contribution_usd" in out:
        out["contribution_per_avail_hour"] = safe_ratio(out["contribution_usd"], out["available_hours"])
    return out
