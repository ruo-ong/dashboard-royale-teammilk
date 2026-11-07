"""A1 - the general manager's list: the machines with the lowest total house win, Jan 1 - Jun 30 2025.

Run:  python -m tasks.a1_manager_list           -> outputs/a1_manager_list.parquet (bottom 25, bottom 10 flagged)

This is the list we put on trial. Its window is fixed by the challenge (the GM ranked Jan-Jun), so it
does not take --start/--end. Every other machine task does.
"""
from __future__ import annotations

import pandas as pd

from royale.data import load_base
from royale.metrics import summarize
from royale.outputs import write_output

MANAGER_START, MANAGER_END = "2025-01-01", "2025-06-30"
LIST_SIZE = 10
CONTEXT_SIZE = 25

COLUMNS = ["house_win_rank", "machine_id", "in_manager_10", "zone_id", "bank_id", "theme", "manufacturer",
           "days_on_floor", "availability", "coin_in_usd", "theo_usd", "house_win_usd"]


def compute(base: pd.DataFrame | None = None, size: int = CONTEXT_SIZE) -> pd.DataFrame:
    """Bottom `size` machines by total house win over the manager's window (on-floor days only)."""
    base = load_base(MANAGER_START, MANAGER_END) if base is None else base
    by_machine = summarize(base, "machine_id")
    attrs = base.sort_values("gaming_date").groupby("machine_id")[["zone_id", "bank_id", "theme", "manufacturer"]].last()
    out = by_machine.merge(attrs, on="machine_id").sort_values(["house_win_usd", "machine_id"]).head(size)
    out["house_win_rank"] = range(1, len(out) + 1)
    out["in_manager_10"] = out["house_win_rank"] <= LIST_SIZE
    return out[COLUMNS].reset_index(drop=True)


def manager_ten(base: pd.DataFrame | None = None) -> list[str]:
    """The 10 machine IDs on the GM's replacement list, lowest house win first."""
    return compute(base, LIST_SIZE)["machine_id"].tolist()


def main() -> None:
    out = compute()
    write_output("a1_manager_list", out)
    show = out.head(LIST_SIZE).copy()
    for col in ["coin_in_usd", "theo_usd", "house_win_usd"]:
        show[col] = show[col].map("${:,.0f}".format)
    show["availability"] = show["availability"].map("{:.1%}".format)
    print(show.drop(columns=["in_manager_10", "manufacturer"]).to_string(index=False))
    print(f"\nWrote outputs/a1_manager_list.parquet ({len(out)} rows; bottom {LIST_SIZE} flagged)")


if __name__ == "__main__":
    main()
