"""A6 - moves as natural experiments: when a machine moved, did its play change the way its new bank predicts?

Run:  python -m tasks.a6_moves [--start 2025-01-01 --end 2025-06-30]   -> outputs/a6_moves.parquet

For each move (machine with 2+ placements): TPAH and occupancy in the 28 gaming days before vs after, skipping
the move day (the only day with move downtime). Effect = the machine's change - the whole floor's change over
the same days, so a floor-wide trend is not credited to the move.

Predicted change = destination bank TPAH - origin bank TPAH, both measured on the other machines in those banks
over the 28 days BEFORE the move. Realisation = effect / predicted change: how much of the bank gap a moved
machine actually captures. R3a uses this to scale the benefit of moving machines.
"""
from __future__ import annotations

import pandas as pd

from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.timeutil import to_gaming_date
from royale.util import safe_ratio

WINDOW_DAYS = 28


def _tpah_occ(rows: pd.DataFrame) -> tuple[float, float, int]:
    if rows.empty:
        return float("nan"), float("nan"), 0
    s = summarize(rows).iloc[0]
    return s["tpah"], s["occupancy"], rows["gaming_date"].nunique()


def compute(base: pd.DataFrame) -> pd.DataFrame:
    placements = load("placements")
    moved = placements.groupby("machine_id").filter(lambda g: len(g) > 1).sort_values(["machine_id", "effective_from_utc"])
    rows = []
    for machine_id, group in moved.groupby("machine_id"):
        for _, placement in group.iloc[1:].iterrows():
            move_day = to_gaming_date(placement["effective_from_utc"])
            if pd.isna(move_day) or move_day not in set(base["gaming_date"]):
                continue
            before_days = (base["gaming_date"] >= move_day - pd.Timedelta(days=WINDOW_DAYS)) & (base["gaming_date"] < move_day)
            after_days = (base["gaming_date"] > move_day) & (base["gaming_date"] <= move_day + pd.Timedelta(days=WINDOW_DAYS))
            mine = base["machine_id"] == machine_id
            origin = base.loc[mine & before_days, "bank_id"].mode().iloc[0]
            destination = base.loc[mine & after_days, "bank_id"].mode().iloc[0]

            m_before = _tpah_occ(base[mine & before_days])
            m_after = _tpah_occ(base[mine & after_days])
            f_before = _tpah_occ(base[before_days])
            f_after = _tpah_occ(base[after_days])
            others_before = base[before_days & ~mine]
            origin_tpah = _tpah_occ(others_before[others_before["bank_id"] == origin])[0]
            dest_tpah = _tpah_occ(others_before[others_before["bank_id"] == destination])[0]

            effect = (m_after[0] - m_before[0]) - (f_after[0] - f_before[0])
            predicted = dest_tpah - origin_tpah
            rows.append({
                "machine_id": machine_id, "move_date": move_day,
                "origin_bank": origin, "destination_bank": destination,
                "days_before": m_before[2], "days_after": m_after[2],
                "tpah_before": m_before[0], "tpah_after": m_after[0],
                "occupancy_before": m_before[1], "occupancy_after": m_after[1],
                "floor_tpah_change": f_after[0] - f_before[0],
                "floor_occupancy_change": f_after[1] - f_before[1],
                "tpah_effect": effect,
                "tpah_effect_pct": safe_ratio(effect, m_before[0]),
                "occupancy_effect": (m_after[1] - m_before[1]) - (f_after[1] - f_before[1]),
                "origin_bank_tpah": origin_tpah, "destination_bank_tpah": dest_tpah,
                "predicted_tpah_change": predicted,
                "realisation": safe_ratio(effect, predicted),
                "direction": "weaker -> stronger" if predicted > 0 else "stronger -> weaker",
            })
    out = pd.DataFrame(rows).sort_values("move_date").reset_index(drop=True)
    zone_of = base.drop_duplicates("bank_id").set_index("bank_id")["zone_name"]
    out.insert(3, "origin_zone", out["origin_bank"].map(zone_of))
    out.insert(5, "destination_zone", out["destination_bank"].map(zone_of))
    return out


def summary_sentence(moves: pd.DataFrame) -> str:
    up = moves[moves["direction"] == "weaker -> stronger"]
    if up.empty:
        return "No move went from a weaker bank to a stronger one in this window."
    eff = up["tpah_effect"]
    real = up["realisation"]
    return (f"{len(up)} of {len(moves)} moves went to a stronger bank. Net of the floor trend, TPAH changed by "
            f"${eff.mean():+.2f}/h on average (range ${eff.min():+.2f} to ${eff.max():+.2f}), capturing "
            f"{real.mean():.0%} of the predicted bank gap (range {real.min():.0%} to {real.max():.0%}). "
            f"With only {len(up)} moves this is a rough calibration, not a precise estimate.")


def main() -> None:
    args = window_args("A6 moves as natural experiments")
    moves = compute(load_base(args.start, args.end))
    write_output("a6_moves", moves)
    cols = ["machine_id", "move_date", "origin_zone", "destination_zone", "days_before", "days_after",
            "tpah_before", "tpah_after", "floor_tpah_change", "tpah_effect", "predicted_tpah_change", "realisation",
            "occupancy_effect"]
    show = moves[cols].copy()
    show["move_date"] = show["move_date"].dt.strftime("%b %d")
    print(show.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print("\n" + summary_sentence(moves))
    print("Wrote outputs/a6_moves.parquet")


if __name__ == "__main__":
    main()
