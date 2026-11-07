"""Loading data. Every analysis task should load through here so filters are applied the same way.

    from royale.data import load
    md = load("machine_day", start="2025-01-01", end="2025-03-31")   # on-floor rows only, by default
    calendar = load("calendar_day")

    from royale.data import con
    con().sql("SELECT zone_id, SUM(theo_usd) FROM prepared_daily_view GROUP BY 1").df()
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd

from royale.paths import TABLES, table_path

# Machine tables that contain off-floor rows, and the SQL condition that keeps on-floor rows only.
# machine_day / prepared_daily_view have one row per machine per day, including 1,018 days before
# install or after retirement (meter_status 'not_installed' / 'retired'). Those are NOT zero sales.
ON_FLOOR_FILTER = {
    "machine_day": "meter_status = 'reported'",
    "prepared_daily_view": "meter_status = 'reported'",
    "machine_hour": "active",  # machine_hour has no meter_status; it only holds installed hours
}

DateLike = str | dt.date | pd.Timestamp | None


def _date_literal(value: DateLike) -> str:
    return pd.Timestamp(value).date().isoformat()


def _columns_of(path) -> list[str]:
    return [row[0] for row in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]


def load(
    name: str,
    start: DateLike = None,
    end: DateLike = None,
    on_floor: bool = True,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Load one table as a DataFrame.

    start / end: inclusive gaming dates. Only allowed for tables with a `gaming_date` column, so a
                 date filter is never silently ignored. Judges change the analysis period, so pass
                 these through instead of hard-wiring Jan-Jun.
    on_floor:    for machine_day, prepared_daily_view and machine_hour, drop rows where the machine
                 was not on the floor (default True). Ignored for other tables.
    columns:     optional list of columns to read.
    """
    path = table_path(name)
    available = _columns_of(path)
    where = []
    if on_floor and name in ON_FLOOR_FILTER:
        where.append(ON_FLOOR_FILTER[name])
    if start is not None or end is not None:
        if "gaming_date" not in available:
            raise ValueError(f"{name} has no gaming_date column; filter it by its own timestamp instead")
        if start is not None:
            where.append(f"gaming_date >= DATE '{_date_literal(start)}'")
        if end is not None:
            where.append(f"gaming_date <= DATE '{_date_literal(end)}'")
    if columns:
        missing = [c for c in columns if c not in available]
        if missing:
            raise KeyError(f"{name} has no column(s) {missing}")
        select = ", ".join(f'"{c}"' for c in columns)
    else:
        select = "*"
    sql = f"SELECT {select} FROM read_parquet('{path}')"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return duckdb.sql(sql).df()


def window(df: pd.DataFrame, start: DateLike = None, end: DateLike = None, col: str = "gaming_date") -> pd.DataFrame:
    """Filter an already-loaded DataFrame to an inclusive date window."""
    dates = pd.to_datetime(df[col])
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return df[mask]


def con(include_outputs: bool = True) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with every raw table (and every built output) registered as a view.

    Raw views are unfiltered: add `WHERE meter_status = 'reported'` yourself on machine tables,
    or query `machine_day_base`, which is on-floor only.
    """
    from royale.paths import OUTPUTS

    connection = duckdb.connect()
    for table, path in TABLES.items():
        connection.sql(f"CREATE VIEW \"{table}\" AS SELECT * FROM read_parquet('{path}')")
    if include_outputs:
        for path in sorted(OUTPUTS.glob("*.parquet")):
            if path.stem in TABLES:
                continue
            connection.sql(f"CREATE VIEW \"{path.stem}\" AS SELECT * FROM read_parquet('{path}')")
    return connection
