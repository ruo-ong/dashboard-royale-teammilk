"""Workstream R (Q6) - which actions would we fund with $100,000 for July 1-30, and how would we know they worked?

Run after every other task:  python -m tasks.r_plan
  R1 r1_costs          every action x quantity: cost with the guide's formula, effective days in July
  R2/R3 r3_benefits    every candidate unit (action x target): 30-day theo benefit low / mid / high, evidence claim IDs
                       (actions with no supporting finding are listed with the reason they were dropped)
  R4 portfolio         the chosen actions (up to 3 types) within $100k, plus what we keep
  R5 r5_sensitivity    each funded action at 50/100/150% of its benefit, break-even, a 7-day lead slip
  R6 r6_measurement    metric, comparison group, check date, success threshold, what happens if it fails
  R7 r7_tradeoffs      what we chose not to fund and why; risks; the amount kept

Budget formula (guide): cost = quantity x (unit cost + daily cost x max(0, 30 - lead days)).
Benefits are in theo (expected house win) over the days left after the lead time, minus the action's own downtime.
"""
from __future__ import annotations

from itertools import combinations, product

import numpy as np
import pandas as pd

from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import read_output, write_output

BUDGET = 100_000
HORIZON = 30
MAX_TYPES = 3
MOVE_DESTINATIONS_EXCLUDED_ZONES = {"Z-HL"}   # high-limit room slots need high-limit games
LAST_30 = ("2025-06-01", "2025-06-30")         # recent level used for July rates


def r1_costs() -> pd.DataFrame:
    cat = load("action_catalog")
    rows = []
    for a in cat.itertuples():
        eff = max(0, HORIZON - a.lead_days)
        for q in range(1, a.quantity_limit + 1):
            cost = q * (a.unit_cost_cents + a.recurring_cost_cents_per_day * eff) / 100
            rows.append({"action_type_id": a.action_type_id, "name": a.name, "unit": a.unit, "quantity": q,
                         "lead_days": a.lead_days, "effective_days": eff, "downtime_minutes": a.downtime_minutes,
                         "quantity_limit": a.quantity_limit, "incompatibility_group": a.incompatibility_group,
                         "cost_usd": cost, "unit_cost_usd": cost / q})
    out = pd.DataFrame(rows)
    lease = out.query("action_type_id == 'A-REPLACE-LEASE' and quantity == 1")["cost_usd"].iloc[0]
    assert abs(lease - 3380) < 0.01, f"Lease example should cost $3,380, got {lease}"
    return out


def _unit(action, target, cost, low, mid, high, claims, note):
    return {"action_type_id": action, "target": target, "unit_cost_usd": cost, "benefit_low_usd": low,
            "benefit_mid_usd": mid, "benefit_high_usd": high, "net_mid_usd": mid - cost, "net_low_usd": low - cost,
            "claim_ids": claims, "how_estimated": note}


def r3_benefits(costs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    c1 = costs[costs["quantity"] == 1].set_index("action_type_id")
    eff = c1["effective_days"]
    down_h = c1["downtime_minutes"] / 60
    base = load_base()
    recent = load_base(*LAST_30)
    m = summarize(base, "machine_id").set_index("machine_id")
    banks = read_output("bank_scores").set_index("bank_id")
    verdicts = read_output("machine_verdicts").set_index("machine_id")
    on_floor = set(recent.loc[recent["gaming_date"] == recent["gaming_date"].max(), "machine_id"])
    hours_per_day = 24 * summarize(recent).iloc[0]["availability"]
    units, dropped = [], []

    # A-INSPECT: every A4 inspection lead. Recovery = hold gap x coin-in/day x days x P(the issue is real).
    leak = read_output("a4_leak")
    for r in leak[leak["inspection_lead"]].itertuples():
        per_day = (r.expected_hold - r.observed_hold) * m.loc[r.machine_id, "coin_in_usd"] / m.loc[r.machine_id, "days_on_floor"]
        days = eff["A-INSPECT"] - down_h["A-INSPECT"] / 24
        units.append(_unit("A-INSPECT", r.machine_id, c1.loc["A-INSPECT", "cost_usd"], 0.25 * per_day * days,
                           0.6 * per_day * days, 0.9 * per_day * days, "A4-01",
                           "hold gap x coin-in/day x effective days x P(real) 25/60/90%; main value is information"))

    # A-PROMO: from M5 (forecast weekend theo x the uplift our own promotions achieved, B2).
    dec = read_output("m5_decision")
    for r in dec[dec["eligible_after_lead"]].sort_values("friday").itertuples():
        units.append(_unit("A-PROMO", f"weekend {r.weekend}", c1.loc["A-PROMO", "cost_usd"], r.promo_theo_uplift_low_usd,
                           r.promo_theo_uplift_usd, r.promo_theo_uplift_high_usd, "B9-05, M-01",
                           "forecast weekend theo (M5) x property-promotion uplift range (B2)"))

    # A-MOVE-MACHINE: Back Forty 'Location' machines into empty slots of stronger banks; scaled by A6 realisation.
    moves = read_output("a6_moves")
    up = moves[moves["direction"] == "weaker -> stronger"]["realisation"]
    real = (0.0, float(up.mean()), float(min(up.max(), 1.0)))
    last = recent[recent["gaming_date"] == recent["gaming_date"].max()]
    used = last.groupby("bank_id").size()
    slots = banks.assign(used=used).fillna({"used": 0})
    slots["empty"] = slots["capacity"] - slots["used"]
    dest = slots[(slots["empty"] > 0) & ~slots["zone_id"].isin(MOVE_DESTINATIONS_EXCLUDED_ZONES)].sort_values("tpah", ascending=False)
    movers = verdicts[(verdicts["verdict"] == "Location") & verdicts.index.isin(on_floor) & (verdicts["zone_id"] == "Z-B40")].copy()
    movers["origin_tpah"] = movers["bank_id"].map(banks["tpah"])
    movers = movers.sort_values("origin_tpah")
    for (mid_, mv), (bank_id, d) in zip(movers.iterrows(), dest.iterrows()):
        gap = d["tpah"] - mv["origin_tpah"]
        if gap <= 0:
            continue
        hours = hours_per_day * eff["A-MOVE-MACHINE"] - down_h["A-MOVE-MACHINE"]
        lost = down_h["A-MOVE-MACHINE"] * m.loc[mid_, "tpah"]
        b = [gap * hours * r - lost for r in real]
        units.append(_unit("A-MOVE-MACHINE", f"{mid_} ({mv['bank_id']}) -> empty slot in {bank_id} ({d['zone_name']})",
                           c1.loc["A-MOVE-MACHINE", "cost_usd"], *b, "A5-01, A6-01, A9-01",
                           f"(destination bank TPAH - origin bank TPAH) x available hours x A6 realisation {real[0]:.0%}/{real[1]:.0%}/{real[2]:.0%}"))

    # A-REPLACE-LEASE / BUY: 'Truly weak' machines; benefit = (bank peer TPAH - machine TPAH) x hours x realisation.
    a5 = read_output("a5_location").set_index("machine_id")
    for action in ["A-REPLACE-LEASE", "A-REPLACE-BUY"]:
        for mid_, v in verdicts[verdicts["verdict"] == "Truly weak"].iterrows():
            if mid_ not in on_floor:
                continue
            gap = a5.loc[mid_, "bank_peer_tpah"] - a5.loc[mid_, "tpah"]
            hours = hours_per_day * eff[action] - down_h[action]
            lost = down_h[action] * a5.loc[mid_, "tpah"]
            b = [gap * hours * r - lost for r in (0.25, 0.5, 1.0)]
            units.append(_unit(action, f"{mid_} ({v['theme']}, {v['zone_name']})", c1.loc[action, "cost_usd"], *b,
                               "A5-03, A9-01", "(bank peer TPAH - machine TPAH) x hours after lead x new-title success 25/50/100%"))

    # A-TECH-SHIFT: C8, per shift.
    tech = read_output("tech_effect").pivot(index="shift", columns="estimate", values="benefit_30d_usd")
    for shift, r in tech.iterrows():
        units.append(_unit("A-TECH-SHIFT", f"{shift} shift", c1.loc["A-TECH-SHIFT", "cost_usd"], r["low"], r["mid"], r["high"],
                           "C-01, C-03", "faults/day x effective days x response saved (1 vs 2 techs) x lost theo per down hour"))

    # A-PREVENTIVE: worst manufacturer; faults avoided x down hours per fault x lost theo per down hour.
    rel = read_output("manufacturer_reliability").iloc[0]
    per_ticket = read_output("c3_ticket_lost_theo")
    f = per_ticket[(per_ticket["event_type"] == "fault_repair") & (per_ticket["manufacturer"] == rel["manufacturer"])]
    per_fault = f["lost_theo_usd"].mean()
    faults_per_day = len(f) / base["gaming_date"].nunique()
    n_mach = base.loc[base["manufacturer"] == rel["manufacturer"], "machine_id"].nunique()
    quiet = read_output("c3_hour_of_week")["index"].min()
    pm_down = n_mach * down_h["A-PREVENTIVE"] * summarize(base[base["manufacturer"] == rel["manufacturer"]]).iloc[0]["tpah"] * quiet
    b = [faults_per_day * eff["A-PREVENTIVE"] * cut * per_fault - pm_down for cut in (0.0, 0.25, 0.5)]
    units.append(_unit("A-PREVENTIVE", rel["manufacturer"], c1.loc["A-PREVENTIVE", "cost_usd"], *b, "C-02",
                       "faults/day x effective days x faults avoided 0/25/50% (only 3 maintenance tickets: weak evidence) x lost theo per fault"))

    # A-WAYFINDING: Back Forty; uplift anchored on the closure effect (access matters), low confidence.
    z = read_output("zone_day")
    b40 = z[(z["zone_id"] == "Z-B40") & z["gaming_date"].between(*map(pd.Timestamp, LAST_30))]["theo_usd"].mean()
    b = [b40 * eff["A-WAYFINDING"] * u for u in (0.0, 0.02, 0.05)]
    units.append(_unit("A-WAYFINDING", "Back Forty", c1.loc["A-WAYFINDING", "cost_usd"], *b, "B9-03, A5-01",
                       "Back Forty theo/day x effective days x uplift 0/2/5% (the closure showed access matters; signage effect unproven)"))

    # A-COMP-PILOT: information, not 30-day theo.
    units.append(_unit("A-COMP-PILOT", "rate pilot with control group", c1.loc["A-COMP-PILOT", "cost_usd"], 0.0, 0.0, 0.0,
                       "E-01, E-02", "no 30-day theo; value is a clean answer on the May 1 comp change (E4: can't tell yet)"))

    dropped += [
        {"action_type_id": "A-MOVE-BANK", "reason": "No empty space for a whole bank: the floor has 6 empty single slots, one per bank."},
        {"action_type_id": "A-COMP-CHANGE", "reason": "No evidence the May 1 rate change helped or hurt (E4); changing again floor-wide "
                                                      "would repeat the problem of having no control group. Conflicts with the pilot."},
        {"action_type_id": "A-SURVEY", "reason": "No decision in this plan depends on what uncarded guests say."},
        {"action_type_id": "A-HOLD", "reason": "Not an action slot: whatever is not spent is kept."},
    ]
    return pd.DataFrame(units), pd.DataFrame(dropped)


def r4_portfolio(units: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Best combination of up to 3 action types x quantities within budget, by mid net benefit (tie: low net)."""
    options = {}
    for action, g in units.groupby("action_type_id"):
        g = g[g["net_mid_usd"] > 0].sort_values("net_mid_usd", ascending=False)
        if g.empty:
            continue
        opts = []
        for q in range(1, len(g) + 1):
            top = g.head(q)
            opts.append({"action_type_id": action, "quantity": q, "cost": top["unit_cost_usd"].sum(),
                         "low": top["benefit_low_usd"].sum(), "mid": top["benefit_mid_usd"].sum(),
                         "high": top["benefit_high_usd"].sum(), "targets": "; ".join(top["target"]),
                         "claim_ids": ", ".join(sorted(set(", ".join(top["claim_ids"]).split(", "))))})
        options[action] = opts
    best, rows = None, []
    for k in range(0, MAX_TYPES + 1):
        for types in combinations(sorted(options), k):
            for choice in product(*(options[t] for t in types)):
                cost = sum(c["cost"] for c in choice)
                if cost > BUDGET:
                    continue
                net_mid = sum(c["mid"] - c["cost"] for c in choice)
                net_low = sum(c["low"] - c["cost"] for c in choice)
                key = (round(net_mid, 2), round(net_low, 2), -cost)
                rows.append({"types": " + ".join(types) or "(keep everything)", "cost": cost, "net_mid": net_mid, "net_low": net_low})
                if best is None or key > best[0]:
                    best = (key, choice)
    chosen = pd.DataFrame(list(best[1]))
    chosen["net_mid"] = chosen["mid"] - chosen["cost"]
    chosen["net_low"] = chosen["low"] - chosen["cost"]
    names = load("action_catalog").set_index("action_type_id")["name"]
    chosen.insert(1, "name", chosen["action_type_id"].map(names))
    keep = BUDGET - chosen["cost"].sum()
    chosen = pd.concat([chosen, pd.DataFrame([{"action_type_id": "A-HOLD", "name": "Preserve budget", "quantity": 1,
                                               "cost": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0, "targets": f"keep ${keep:,.0f}",
                                               "claim_ids": "", "net_mid": 0.0, "net_low": 0.0, "kept_usd": keep}])], ignore_index=True)
    return chosen, pd.DataFrame(rows).sort_values("net_mid", ascending=False).head(25)


def r5_sensitivity(portfolio: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    eff = costs.groupby("action_type_id")["effective_days"].first()
    rows = []
    for r in portfolio[portfolio["action_type_id"] != "A-HOLD"].itertuples():
        e = eff[r.action_type_id]
        slip = max(e - 7, 0) / e if e else 0
        rows.append({"action_type_id": r.action_type_id, "name": r.name, "cost": r.cost,
                     "net_at_50pct": 0.5 * r.mid - r.cost, "net_at_100pct": r.mid - r.cost, "net_at_150pct": 1.5 * r.mid - r.cost,
                     "net_at_low": r.low - r.cost, "net_at_high": r.high - r.cost,
                     "break_even_share_of_mid": r.cost / r.mid if r.mid else np.nan,
                     "net_if_lead_slips_7_days": r.mid * slip - r.cost})
    return pd.DataFrame(rows)


MEASUREMENT = {
    "A-PROMO": dict(metric="Floor theo on the promotion weekend (theo, not house win: luck cannot fake a result)",
                    comparison="The frozen M5 forecast for that weekend, and the same weekend's days in the weeks before",
                    check_date="Monday after each promotion weekend (Jul 21; Jul 28)",
                    success="Theo above forecast by more than the break-even uplift, net of the model's known May-June bias",
                    if_fails="Do not repeat the format; review prize structure before the next quarter's calendar"),
    "A-INSPECT": dict(metric="Paytable / configuration match, then hit-rate z and hold gap on M-1158",
                      comparison="The game's published hit probability and RTP (game_math); the other Desert Gold machines",
                      check_date="Inspection report by Jul 3; payout re-check after 28 days (Jul 31)",
                      success="Mismatch found and fixed, and hit-rate z back within +-3 over the next 28 days",
                      if_fails="If the paytable is correct, escalate to the manufacturer; keep the machine on the watch list, do not replace"),
    "A-MOVE-MACHINE": dict(metric="TPAH and occupancy of each moved machine",
                           comparison="The other Back Forty machines that stayed (difference-in-differences, as in A6)",
                           check_date="28 days after each move (Jul 31)",
                           success="Moved machines gain at least the break-even share of the bank gap, net of the stayers' change",
                           if_fails="Stop moving single machines; treat the Back Forty as a zone problem (access, mix) next quarter"),
    "A-REPLACE-LEASE": dict(metric="TPAH of the new title vs the replaced machine", comparison="Bank peers over the same days",
                            check_date="End of July", success="Peer index of the new title >= 0.9",
                            if_fails="Return the lease; do not extend the title"),
    "A-WAYFINDING": dict(metric="Back Forty entries per sensor-day and TPAH", comparison="Unaffected zones (B4 method)",
                         check_date="Jul 31", success="Back Forty TPAH up vs other zones by the break-even uplift",
                         if_fails="Investigate game mix and layout instead"),
    "A-COMP-PILOT": dict(metric="Theo, visits and comp cost per player", comparison="Randomly assigned control group",
                         check_date="Jul 31", success="Theo per player gain exceeds the extra comp cost",
                         if_fails="Revert the treatment group"),
}


def main() -> None:
    costs = r1_costs()
    write_output("r1_costs", costs)
    units, dropped = r3_benefits(costs)
    write_output("r3_benefits", units)
    write_output("r2_dropped", dropped)
    portfolio, alternatives = r4_portfolio(units)
    write_output("portfolio", portfolio)
    write_output("r4_alternatives", alternatives)
    sens = r5_sensitivity(portfolio, costs)
    write_output("r5_sensitivity", sens)
    meas = pd.DataFrame([{"action_type_id": a, **MEASUREMENT.get(a, {})} for a in portfolio["action_type_id"] if a != "A-HOLD"])
    write_output("r6_measurement", meas)

    funded = set(portfolio["action_type_id"])
    not_funded = units[~units["action_type_id"].isin(funded)].groupby("action_type_id").agg(
        best_net_mid=("net_mid_usd", "max"), how=("how_estimated", "first")).reset_index()
    not_funded["reason"] = [
        f"Costs more than its expected 30-day benefit (best option nets {'-' if n < 0 else '+'}${abs(n):,.0f} at the mid estimate)"
        if n <= 0 else "Positive, but a better use of one of the 3 action slots exists" for n in not_funded["best_net_mid"]]
    trade = pd.concat([not_funded[["action_type_id", "reason"]], dropped], ignore_index=True)
    keep = portfolio.loc[portfolio["action_type_id"] == "A-HOLD", "kept_usd"].iloc[0]
    trade.loc[len(trade)] = {"action_type_id": "RISKS", "reason": (
        "Promotion uplift is measured on two of our own events only; move benefit rests on 3 past moves (realisation "
        "-57% to +195%); the inspection may find nothing (its value is then the information).")}
    trade.loc[len(trade)] = {"action_type_id": "KEPT", "reason": f"${keep:,.0f} kept: no other action clears its cost within 30 days."}
    write_output("r7_tradeoffs", trade)

    print("R1 lease example: $3,380 reproduced")
    print("R3 units:\n" + units[["action_type_id", "target", "unit_cost_usd", "benefit_low_usd", "benefit_mid_usd",
                                  "benefit_high_usd", "net_mid_usd"]].to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
    print("\nR4 portfolio:\n" + portfolio[["action_type_id", "quantity", "cost", "low", "mid", "high", "net_mid", "net_low",
                                           "targets"]].to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
    print("\nR5:\n" + sens.drop(columns=["name"]).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print("\nR7:\n" + trade.to_string(index=False))


if __name__ == "__main__":
    main()
