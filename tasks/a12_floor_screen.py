"""A12 - floor-wide screen: which machines, anywhere on the floor, under-perform once their spot, game and maker
are allowed for?

Run:  python -m tasks.a12_floor_screen [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a12_floor_screen.parquet   one row per machine: actual vs expected, in the whole period and each half

For each machine, "expected" is what the machine estimator (M6: bank + game + manufacturer, fitted on the same period)
predicts for a machine with the same characteristics. The ratio actual / expected is luck-free (theo) and
exposure-free (per available hour), so it isolates the machine itself.

Status (starting thresholds; adjustable):
  Underperforms   below 0.90 of expected over the period AND in each half (consistent, not one bad stretch)
  Watch           below 0.93 of expected over the period (about the bottom 5%), but not consistently below 0.90
  In line         everything else with at least 60 days on the floor
  Too little data fewer than 60 days on the floor
A "game-location fit" flag marks machines whose game also runs below expectation on the other machines in the same
zone: then the remedy is where the game stands, not the individual machine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import load_base
from royale.outputs import read_output, write_output
from tasks.m6_machine_model import MachineModel, machine_table

UNDER = 0.90
WATCH = 0.93
MIN_DAYS = 60
FIT_MIN = 0.95     # the same game's other machines in the zone average below this -> game-location fit issue


def _expected(base: pd.DataFrame) -> pd.DataFrame:
    t = machine_table(base)
    t["expected_tpah"] = MachineModel().fit(t).predict(t)
    t["ratio"] = t["tpah"] / t["expected_tpah"]
    return t


def compute(base: pd.DataFrame) -> pd.DataFrame:
    dates = sorted(base["gaming_date"].unique())
    mid = dates[len(dates) // 2]
    whole = _expected(base)
    h1 = _expected(base[base["gaming_date"] < mid]).set_index("machine_id")["ratio"]
    h2 = _expected(base[base["gaming_date"] >= mid]).set_index("machine_id")["ratio"]
    s = whole.rename(columns={"ratio": "ratio_whole"}).copy()
    s["ratio_first_half"] = s["machine_id"].map(h1)
    s["ratio_second_half"] = s["machine_id"].map(h2)
    s["shortfall_usd"] = (s["expected_tpah"] - s["tpah"]) * s["available_hours"]   # positive = earned less than expected
    eligible = s["days_on_floor"] >= MIN_DAYS
    spread = s.loc[eligible, "ratio_whole"].std()
    s["z"] = (s["ratio_whole"] - 1) / spread

    # Same game, same zone, other machines: is the game itself a poor fit for this area?
    def others_mean(r):
        same = s[(s["theme"] == r["theme"]) & (s["zone_id"] == r["zone_id"]) & (s["machine_id"] != r["machine_id"]) & eligible]
        return np.average(same["ratio_whole"], weights=same["available_hours"]) if len(same) else np.nan
    s["same_game_same_zone_ratio"] = s.apply(others_mean, axis=1)
    s["game_location_fit_issue"] = s["same_game_same_zone_ratio"] < FIT_MIN

    consistent = (s["ratio_whole"] < UNDER) & (s["ratio_first_half"] < UNDER) & (s["ratio_second_half"] < UNDER)
    s["status"] = np.select([~eligible, consistent, s["ratio_whole"] < WATCH], ["Too little data", "Underperforms", "Watch"], "In line")

    # Context from the other tests, so a reader sees every reason at once.
    try:
        v = read_output("machine_verdicts").set_index("machine_id")
        s["inspection_lead"] = s["machine_id"].map(v["inspection_lead"]).fillna(False).astype(bool)
        s["chronic_faults"] = s["machine_id"].map(v["chronic_faults"]).fillna(False).astype(bool)
    except FileNotFoundError:
        s["inspection_lead"] = s["chronic_faults"] = False

    def advice(r):
        if r["status"] == "Too little data":
            return "Not enough time on the floor to judge."
        if r["inspection_lead"]:
            return "Inspect its payout settings first (see the payout check)."
        if r["status"] == "Underperforms" and r["game_location_fit_issue"]:
            return "Its game also runs below expectation elsewhere in this area: consider moving the game to a busier area before replacing the machine."
        if r["status"] == "Underperforms":
            return "Earns consistently less than comparable machines: check its condition and set-up, then consider replacement."
        if r["status"] == "Watch":
            return "Slightly below expectation, but not consistently: review again next quarter."
        return "Performing as expected for its spot and game."
    s["advice"] = s.apply(advice, axis=1)
    order = {"Underperforms": 0, "Watch": 1, "In line": 2, "Too little data": 3}
    keep = ["machine_id", "status", "advice", "zone_name", "bank_id", "theme", "manufacturer", "days_on_floor", "tpah",
            "expected_tpah", "ratio_whole", "ratio_first_half", "ratio_second_half", "z", "shortfall_usd",
            "same_game_same_zone_ratio", "game_location_fit_issue", "inspection_lead", "chronic_faults", "available_hours"]
    return s[keep].sort_values(["status", "ratio_whole"], key=lambda c: c.map(order) if c.name == "status" else c).reset_index(drop=True)


def main() -> None:
    args = window_args("A12 floor-wide screen")
    screen = compute(load_base(args.start, args.end))
    write_output("a12_floor_screen", screen)
    elig = screen[screen["status"] != "Too little data"]
    print(f"{len(elig)} machines with {MIN_DAYS}+ days; actual/expected: median {elig['ratio_whole'].median():.3f}, "
          f"spread (sd) {elig['ratio_whole'].std():.3f}; 90% between {elig['ratio_whole'].quantile(.05):.3f} and {elig['ratio_whole'].quantile(.95):.3f}")
    print("Status:", screen["status"].value_counts().to_dict())
    show = screen[screen["status"].isin(["Underperforms", "Watch"])]
    print(show[["machine_id", "status", "zone_name", "theme", "ratio_whole", "ratio_first_half", "ratio_second_half", "shortfall_usd",
                "same_game_same_zone_ratio", "game_location_fit_issue"]].to_string(index=False, float_format=lambda x: f"{x:,.3f}"))


if __name__ == "__main__":
    main()
