"""F4 - build outputs/machine_day_base.parquet: one row per ON-FLOOR machine x gaming date.

Run from the repo root:   python -m tasks.f4_machine_day_base

Start from machine_day (all meters, incl. sum_bet_squared and payout_positive_spins), take zone/bank,
calendar, events and supplied costs from prepared_daily_view on the same key (1:1, so no double counting),
add game math per config and machine attributes. Everything is in dollars and hours.
The build fails loudly if the totals do not reconcile.
"""
from __future__ import annotations

import time

import duckdb
import pandas as pd

from royale.outputs import output_path, write_output
from royale.paths import ROOT, table_path

EXPECTED_ROWS = 56_110 - 1_018  # every machine-day minus the off-floor days
CENT = 0.01

BUILD_SQL = """
SELECT
    -- keys and calendar
    md.machine_id,
    md.gaming_date,
    pv.month,
    pv.local_weekday,
    pv.is_weekend,
    pv.federal_holiday,
    pv.events_active,
    -- place (location at day start)
    md.location_id,
    pv.bank_id,
    pv.zone_id,
    pv.zone_name,
    -- machine and game
    md.config_id,
    gm.theme,
    m.manufacturer,
    m.lease_class,
    m.install_date,
    m.retire_date,
    CAST(gm.configured_rtp AS DOUBLE)              AS configured_rtp,
    gm.volatility_class,
    CAST(gm.payout_multiplier_variance AS DOUBLE)  AS payout_multiplier_variance,
    CAST(gm.hit_probability AS DOUBLE)             AS hit_probability,
    -- hours (machine_day seconds only count time on the floor)
    md.scheduled_seconds / 3600.0                          AS on_floor_hours,
    md.available_seconds / 3600.0                          AS available_hours,
    (md.scheduled_seconds - md.available_seconds) / 3600.0 AS down_hours,
    md.occupied_seconds / 3600.0                           AS occupied_hours,
    -- play, in dollars (converted once, here)
    md.paid_spins,
    md.payout_positive_spins,
    md.coin_in_cents / 100.0                            AS coin_in_usd,
    md.payout_cents / 100.0                             AS payout_usd,
    md.house_win_cents / 100.0                          AS house_win_usd,
    CAST(md.theo_cents AS DOUBLE) / 100.0               AS theo_usd,
    (md.house_win_cents - CAST(md.theo_cents AS DOUBLE)) / 100.0 AS luck_residual_usd,
    -- luck pieces: add these up over any period, then take sqrt / ratios (see royale.metrics)
    -- variance of the day's payout = sum(bet^2) x per-spin variance of payout/bet  (cents^2 -> dollars^2)
    md.sum_bet_squared * CAST(gm.payout_multiplier_variance AS DOUBLE) / 10000.0 AS luck_var_usd2,
    md.paid_spins * CAST(gm.hit_probability AS DOUBLE)                            AS expected_hits,
    md.paid_spins * CAST(gm.hit_probability AS DOUBLE)
                  * (1 - CAST(gm.hit_probability AS DOUBLE))                      AS hit_var,
    -- carded (tracked) subset
    md.carded_coin_in_cents / 100.0                AS carded_coin_in_usd,
    md.carded_payout_cents / 100.0                 AS carded_payout_usd,
    md.carded_spins,
    CAST(md.carded_theo_cents AS DOUBLE) / 100.0   AS carded_theo_usd,
    -- supplied costs
    CAST(pv.lease_cost_usd AS DOUBLE)   AS lease_cost_usd,
    CAST(pv.service_cost_usd AS DOUBLE) AS service_cost_usd,
    CAST(pv.power_cost_usd AS DOUBLE)   AS power_cost_usd,
    CAST(pv.repair_cost_usd AS DOUBLE)  AS repair_cost_usd,
    CAST(pv.lease_cost_usd + pv.service_cost_usd + pv.power_cost_usd + pv.repair_cost_usd AS DOUBLE)
                                        AS supplied_costs_usd,
    CAST(pv.contribution_after_supplied_costs_usd AS DOUBLE) AS contribution_usd,
    -- operations
    pv.faults_opened
FROM read_parquet('{machine_day}') AS md
JOIN read_parquet('{prepared}') AS pv USING (machine_id, gaming_date)
JOIN read_parquet('{game_math}') AS gm ON gm.config_id = md.config_id
JOIN read_parquet('{machines}') AS m ON m.machine_id = md.machine_id
WHERE md.meter_status = 'reported'
ORDER BY md.machine_id, md.gaming_date
"""


def build() -> pd.DataFrame:
    sql = BUILD_SQL.format(
        machine_day=table_path("machine_day"),
        prepared=table_path("prepared_daily_view"),
        game_math=table_path("game_math"),
        machines=table_path("machines"),
    )
    return duckdb.sql(sql).df()


def reconcile(base: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """Return (check, passed, detail) for every reconciliation check."""
    con = duckdb.connect()
    con.register("base", base)
    for name in ("prepared_daily_view", "property_day", "calendar_day"):
        con.sql(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{table_path(name)}')")

    def one(sql: str):
        return con.sql(sql).fetchall()[0]

    results = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        results.append((name, bool(passed), detail))

    keys_unique, keys_null = one(
        "SELECT count(*) - count(DISTINCT (machine_id, gaming_date)), "
        "count(*) FILTER (WHERE machine_id IS NULL OR gaming_date IS NULL) FROM base"
    )
    check("row count", len(base) == EXPECTED_ROWS, f"{len(base):,} rows (expected {EXPECTED_ROWS:,})")
    check("unique, non-null keys", keys_unique == 0 and keys_null == 0, f"{keys_unique} duplicates, {keys_null} null keys")

    b_hw, b_theo, b_ci, b_avail = one(
        "SELECT sum(house_win_usd), sum(theo_usd), sum(coin_in_usd), sum(available_hours) FROM base"
    )
    p_hw, p_theo, p_ci = one(
        "SELECT sum(house_win_usd)::DOUBLE, sum(theo_usd)::DOUBLE, sum(coin_in_usd)::DOUBLE "
        "FROM prepared_daily_view WHERE meter_status = 'reported'"
    )
    d_hw, d_theo, d_ci, d_avail = one(
        "SELECT sum(house_win_usd)::DOUBLE, sum(theo_usd)::DOUBLE, sum(coin_in_usd)::DOUBLE, "
        "sum(available_machine_hours) FROM property_day"
    )
    for label, ours, prepared, prop in [
        ("house win", b_hw, p_hw, d_hw),
        ("theo", b_theo, p_theo, d_theo),
        ("coin-in", b_ci, p_ci, d_ci),
    ]:
        gap = max(abs(ours - prepared), abs(ours - prop))
        check(f"{label} total matches prepared_daily_view and property_day", gap <= CENT,
              f"${ours:,.2f}; max gap ${gap:.6f}")
    check("available hours match property_day", abs(b_avail - d_avail) < 1e-6,
          f"{b_avail:,.2f} h vs {d_avail:,.2f} h")

    bad_luck, bad_contrib = one(
        "SELECT count(*) FILTER (WHERE abs(luck_residual_usd - (house_win_usd - theo_usd)) > 1e-6), "
        "count(*) FILTER (WHERE abs(contribution_usd - (house_win_usd - supplied_costs_usd)) > 0.005) FROM base"
    )
    check("luck residual = house win - theo on every row", bad_luck == 0, f"{bad_luck} bad rows")
    check("contribution = house win - supplied costs on every row", bad_contrib == 0, f"{bad_contrib} bad rows")

    nulls = one(
        "SELECT count(*) FILTER (WHERE zone_id IS NULL OR bank_id IS NULL OR location_id IS NULL "
        "OR configured_rtp IS NULL OR payout_multiplier_variance IS NULL OR hit_probability IS NULL "
        "OR manufacturer IS NULL) FROM base"
    )[0]
    check("no nulls in location / game-math / machine columns", nulls == 0, f"{nulls} rows with nulls")

    over = one(
        "SELECT count(*) FILTER (WHERE b.on_floor_hours > c.scheduled_seconds / 3600.0 + 1e-9 "
        "OR b.available_hours > b.on_floor_hours + 1e-9 OR b.occupied_hours > b.available_hours + 1e-9) "
        "FROM base b JOIN calendar_day c USING (gaming_date)"
    )[0]
    check("occupied <= available <= on-floor <= calendar hours", over == 0, f"{over} rows out of order")

    dst = one("SELECT max(on_floor_hours) FROM base WHERE gaming_date = DATE '2025-03-08'")[0]
    check("DST day is 23 hours", abs(dst - 23.0) < 1e-9, f"max on-floor hours on 2025-03-08 = {dst}")
    return results


def main() -> None:
    started = time.perf_counter()
    base = build()
    results = reconcile(base)
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}  ({detail})")
    failed = [name for name, passed, _ in results if not passed]
    if failed:
        raise SystemExit(f"Reconciliation failed: {failed}. Nothing was written.")
    write_output("machine_day_base", base)
    built = time.perf_counter() - started

    load_started = time.perf_counter()
    pd.read_parquet(output_path("machine_day_base"))
    load_seconds = time.perf_counter() - load_started
    path = output_path("machine_day_base")
    print(f"\nWrote {path.relative_to(ROOT)}: {len(base):,} rows x {base.shape[1]} columns, "
          f"{path.stat().st_size / 1e6:.1f} MB, built in {built:.1f} s")
    print(f"{'PASS' if load_seconds < 2 else 'FAIL'}: loads in {load_seconds:.2f} s (target < 2 s)")


if __name__ == "__main__":
    main()
