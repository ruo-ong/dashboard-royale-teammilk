"""A9 - verdicts and the real replacement list.

Run after the A tasks, b_demand and c_downtime:  python -m tasks.a9_verdicts [--start ... --end ...]
  -> outputs/machine_verdicts.parquet     one row per machine: verdict, reason, advice, secondary flags
  -> outputs/a9_list_comparison.parquet   the manager's list vs ours: who stays, drops, is new, and why

Verdict = the largest negative piece of the A8 decomposition, with these overrides and rules:
  Inspect             A4 inspection lead (checked first: never replace a machine that may just be mis-set)
  Watch list          fewer than 60 days on the floor: not enough evidence for a verdict
  Fine                earned at least as much as a typical machine
  Short time on floor / Downtime / Location / Unlucky    the largest negative piece
  Truly weak          largest piece is the machine itself AND peer index < 0.7 AND play volume < 0.8 x peers
  Low-hold game       largest piece is the machine itself, but players use it as much as its neighbours (A5):
                      its low theo is the game's payback setting, a pricing choice, not a broken machine
If the machine piece does not meet "Truly weak", the next-largest negative piece decides.
Secondary flags keep the other evidence visible (chronic faults, closure zone, thin peer group, ...).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import load_base
from royale.outputs import read_output, write_output
from tasks import a2_exposure, a4_leak, a5_location, a8_decomposition
from tasks.a1_manager_list import manager_ten

WEAK_PEER_INDEX = 0.70
WEAK_VOLUME_INDEX = 0.80
GAME_WEAK_EVERYWHERE = 0.80   # the game's floor-wide TPAH below 80% of the median machine's

PIECE_VERDICT = {"short_exposure_usd": "Short time on floor", "downtime_usd": "Downtime",
                 "location_usd": "Location", "machine_itself_usd": "Machine", "luck_usd": "Unlucky"}
ADVICE = {
    "Inspect": "Inspect and verify the paytable (A-INSPECT) before any replacement decision.",
    "Watch list": "Too few days on the floor for a verdict; re-check after a full window.",
    "Fine": "Keep.",
    "Short time on floor": "Keep; it was not on the floor for the whole window. Judge it per available hour.",
    "Downtime": "Keep; fix reliability (repairs, preventive maintenance) rather than replace.",
    "Location": "Do not replace; the spot is the problem (move it, or improve the zone).",
    "Unlucky": "Keep; ordinary bad luck, no action.",
    "Low-hold game": "Keep; players use it as much as its neighbours. Its low theo is the game's payback setting.",
    "Truly weak": "Replace candidate.",
}


def compute(base: pd.DataFrame, start=None, end=None, chronic: pd.DataFrame | None = None,
            closure_zones: set[str] | None = None, manager_ids: list[str] | None = None) -> pd.DataFrame:
    ids = manager_ten() if manager_ids is None else manager_ids
    exposure = a2_exposure.compute(base, start, end, ids)
    leak, _ = a4_leak.compute(base, ids)
    location, _, _ = a5_location.compute(base, ids)
    dec = a8_decomposition.compute(base, start, end, ids, location)

    v = dec.merge(location[["machine_id", "zone_name", "peer_index", "volume_peer_index", "low_hold_game",
                            "thin_peer_group", "location_read", "game_floor_tpah", "n_peers"]], on="machine_id")
    v = v.merge(exposure[["machine_id", "days_on_floor", "low_evidence", "partial_window"]], on="machine_id")
    v = v.merge(leak[["machine_id", "inspection_lead", "luck_z", "hit_rate_z"]], on="machine_id")
    median_tpah = v["tpah"].median()
    v["game_weak_everywhere"] = v["game_floor_tpah"] < GAME_WEAK_EVERYWHERE * median_tpah
    v["chronic_faults"] = v["machine_id"].isin(set(chronic.loc[chronic["chronic"], "machine_id"])) if chronic is not None else False
    v["closure_zone"] = v["zone_id"].isin(closure_zones or set())

    def decide(r):
        if r["inspection_lead"]:
            return "Inspect", "inspection_lead"
        if r["low_evidence"]:
            return "Watch list", ""
        if r["gap_usd"] >= 0:
            return "Fine", ""
        pieces = sorted(((r[c], c) for c in PIECE_VERDICT), key=lambda x: x[0])
        for value, col in pieces:
            if value >= 0:
                break
            if col != "machine_itself_usd":
                return PIECE_VERDICT[col], col
            if r["low_hold_game"]:
                return "Low-hold game", col
            if r["peer_index"] < WEAK_PEER_INDEX and r["volume_peer_index"] < WEAK_VOLUME_INDEX:
                return "Truly weak", col
        return "Fine", ""

    decided = v.apply(decide, axis=1, result_type="expand")
    v["verdict"], v["deciding_piece"] = decided[0], decided[1]

    def money(x: float) -> str:
        return f"{'-' if x < 0 else '+'}${abs(x) / 1000:,.1f}k"

    def reason(r) -> str:
        if r["verdict"] == "Inspect":
            core = f"payout pattern differs from its game math (hit-rate z {r['hit_rate_z']:+.0f}, luck z {r['luck_z']:+.1f})"
        elif r["verdict"] == "Watch list":
            core = f"only {r['days_on_floor']} days on the floor"
        elif r["verdict"] == "Fine":
            core = f"earned {money(r['gap_usd'])} vs a typical machine" if r["gap_usd"] >= 0 else "no piece clearly to blame"
        else:
            label = "machine itself" if r["deciding_piece"] == "machine_itself_usd" else PIECE_VERDICT[r["deciding_piece"]].lower()
            core = f"{label} {money(r[r['deciding_piece']])} (overall gap vs a typical machine {money(r['gap_usd'])})"
            if r["deciding_piece"] == "machine_itself_usd":
                core += f"; peer index {r['peer_index']:.2f}, play volume {r['volume_peer_index']:.2f}x its neighbours"
        extras = []
        if r["closure_zone"] and r["verdict"] in ("Location", "Truly weak"):
            extras.append("its zone lost access during the Mar 3-Apr 6 walkway closure, so part of the location gap was temporary")
        if r["chronic_faults"]:
            extras.append("chronic faults")
        if r["thin_peer_group"]:
            extras.append(f"only {int(r['n_peers'])} bank peers")
        return f"{r['verdict']}: {core}" + (f"; {'; '.join(extras)}" if extras else "") + "."

    v["reason"] = v.apply(reason, axis=1)
    v["advice"] = v["verdict"].map(ADVICE)
    weak = v["verdict"] == "Truly weak"
    v.loc[weak & v["game_weak_everywhere"], "advice"] = "Replace the title: the same game is weak across the floor."
    v.loc[weak & ~v["game_weak_everywhere"], "advice"] = "Replace the machine."
    v["replace_rank"] = np.nan
    ranked = v[weak].sort_values("machine_itself_usd").index
    v.loc[ranked, "replace_rank"] = range(1, len(ranked) + 1)
    v["on_our_list"] = v["replace_rank"] <= 10
    v["in_manager_10"] = v["machine_id"].isin(ids)
    keep = ["machine_id", "zone_id", "zone_name", "bank_id", "theme", "verdict", "reason", "advice", "replace_rank",
            "on_our_list", "in_manager_10", "gap_usd", "short_exposure_usd", "downtime_usd", "location_usd",
            "machine_volume_usd", "machine_hold_usd", "machine_itself_usd", "luck_usd", "tpah", "peer_index",
            "volume_peer_index", "luck_z", "hit_rate_z", "days_on_floor", "inspection_lead", "low_evidence",
            "partial_window", "low_hold_game", "game_weak_everywhere", "chronic_faults", "closure_zone", "thin_peer_group"]
    return v[keep].sort_values(["in_manager_10", "gap_usd"], ascending=[False, True]).reset_index(drop=True)


def list_comparison(verdicts: pd.DataFrame, manager_ids: list[str]) -> pd.DataFrame:
    rows = []
    for mid in manager_ids:
        r = verdicts.set_index("machine_id").loc[mid]
        status = "stays" if r["on_our_list"] else "drops"
        rows.append({"machine_id": mid, "status": status, "verdict": r["verdict"], "why": r["reason"], "advice": r["advice"]})
    for _, r in verdicts[verdicts["on_our_list"] & ~verdicts["in_manager_10"]].sort_values("replace_rank").iterrows():
        rows.append({"machine_id": r["machine_id"], "status": "new", "verdict": r["verdict"], "why": r["reason"], "advice": r["advice"]})
    return pd.DataFrame(rows)


def main() -> None:
    args = window_args("A9 verdicts")
    base = load_base(args.start, args.end)
    chronic = read_output("c7_chronic")
    closure = read_output("closure_effect")
    zones = set(closure["affected_zones"].iloc[0].split(", "))
    ids = manager_ten()
    verdicts = compute(base, args.start, args.end, chronic, zones, ids)
    write_output("machine_verdicts", verdicts)
    comp = list_comparison(verdicts, ids)
    write_output("a9_list_comparison", comp)

    print("Floor-wide verdicts:", verdicts["verdict"].value_counts().to_dict())
    print("\nThe manager's 10:")
    for r in comp[comp["status"] != "new"].itertuples():
        print(f"  {r.machine_id} [{r.status}] {r.why}")
    new = comp[comp["status"] == "new"]
    print(f"\nOur replacement list ({int(verdicts['on_our_list'].sum())} machines, {len(new)} not on the manager's list):")
    for r in new.itertuples():
        print(f"  {r.machine_id} {r.why} -> {r.advice}")


if __name__ == "__main__":
    main()
