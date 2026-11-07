"""A11 - profit view: which machines lose money even with average luck?

Run:  python -m tasks.a11_profit [--start 2025-01-01 --end 2025-06-30]   -> outputs/a11_profit.parquet

Contribution = house win - supplied costs (lease, service, power, repair). Supplied costs are partial: no rent,
tax, depreciation or full staffing, so always say "contribution after supplied costs".
Expected contribution = theo - supplied costs: the same thing with average luck, which is the fair basis for
replacement economics (R3c). The plan's flag: a LEASED machine whose lease + service cost exceeds its theo.
"""
from __future__ import annotations

import pandas as pd

from royale.cli import window_args
from royale.data import load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.util import safe_ratio
from tasks.a1_manager_list import manager_ten


def compute(base: pd.DataFrame, manager_ids: list[str] | None = None) -> pd.DataFrame:
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    costs = ["lease_cost_usd", "service_cost_usd", "power_cost_usd", "repair_cost_usd"]
    m = summarize(base, "machine_id")[["machine_id", "days_on_floor", "available_hours", "theo_usd", "house_win_usd",
                                       "supplied_costs_usd", "contribution_usd", "tpah"]]
    m = m.merge(base.groupby("machine_id")[costs].sum().reset_index(), on="machine_id")
    attrs = base.sort_values("gaming_date").groupby("machine_id")[["zone_name", "bank_id", "theme", "manufacturer",
                                                                    "lease_class"]].last().reset_index()
    m = m.merge(attrs, on="machine_id")
    m["contribution_per_avail_hour"] = safe_ratio(m["contribution_usd"], m["available_hours"])
    m["expected_contribution_usd"] = m["theo_usd"] - m["supplied_costs_usd"]
    m["expected_contribution_per_avail_hour"] = safe_ratio(m["expected_contribution_usd"], m["available_hours"])
    m["lease_service_usd"] = m["lease_cost_usd"] + m["service_cost_usd"]
    m["lease_service_share_of_theo"] = safe_ratio(m["lease_service_usd"], m["theo_usd"])
    m["leased"] = m["lease_class"].str.startswith("leased")
    m["loses_money_at_average_luck"] = m["expected_contribution_usd"] < 0
    m["lease_exceeds_theo"] = m["leased"] & (m["lease_service_usd"] > m["theo_usd"])
    m["in_manager_10"] = m["machine_id"].isin(manager_ids)
    return m.sort_values("expected_contribution_per_avail_hour").reset_index(drop=True)


def main() -> None:
    args = window_args("A11 profit view")
    profit = compute(load_base(args.start, args.end))
    write_output("a11_profit", profit)

    print("Supplied costs by lease class:")
    by_class = profit.groupby("lease_class").agg(machines=("machine_id", "size"), theo=("theo_usd", "sum"),
                                                 lease_service=("lease_service_usd", "sum"),
                                                 expected_contribution=("expected_contribution_usd", "sum"))
    by_class["lease_service_share_of_theo"] = by_class["lease_service"] / by_class["theo"]
    print(by_class.to_string(float_format=lambda v: f"{v:,.2f}"))

    flagged = profit[profit["lease_exceeds_theo"]]
    print(f"\nLeased machines whose lease + service exceed their theo: {len(flagged)}")
    if len(flagged):
        print(flagged[["machine_id", "zone_name", "theme", "lease_class", "theo_usd", "lease_service_usd",
                       "expected_contribution_usd"]].to_string(index=False, float_format=lambda v: f"{v:,.0f}"))
    losing = profit[profit["loses_money_at_average_luck"]]
    print(f"Machines with negative expected contribution (any lease class): {len(losing)}")

    print("\nThe manager's 10:")
    print(profit[profit["in_manager_10"]][["machine_id", "lease_class", "theo_usd", "supplied_costs_usd",
                                           "expected_contribution_usd", "contribution_usd",
                                           "expected_contribution_per_avail_hour"]]
          .to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print("\nWrote outputs/a11_profit.parquet")


if __name__ == "__main__":
    main()
