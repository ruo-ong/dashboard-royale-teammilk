"""F2 'done when': every shared helper shown working on real rows, incl. a 2 a.m. timestamp and the DST day."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from royale.data import con, load, window
from royale.paths import TABLES
from royale.timeutil import to_gaming_date, to_shift
from royale.util import cents_to_usd, safe_ratio


# ---------- loading ----------

def test_all_31_tables_registered():
    assert len(TABLES) == 31
    assert {"machine_day", "prepared_daily_view", "calendar_day", "shift_roster"} <= set(TABLES)


def test_off_floor_rows_dropped_by_default():
    assert len(load("machine_day")) == 55_092
    assert len(load("machine_day", on_floor=False)) == 56_110
    assert len(load("prepared_daily_view")) == 55_092
    assert set(load("machine_day", columns=["meter_status"])["meter_status"]) == {"reported"}


def test_date_window_is_inclusive():
    march = load("calendar_day", start="2025-03-01", end="2025-03-31")
    assert len(march) == 31
    assert march["gaming_date"].min() == pd.Timestamp("2025-03-01")
    assert march["gaming_date"].max() == pd.Timestamp("2025-03-31")
    one_day = load("machine_day", start=dt.date(2025, 3, 8), end=dt.date(2025, 3, 8))
    assert one_day["gaming_date"].nunique() == 1


def test_window_on_loaded_frame():
    cal = load("calendar_day")
    assert len(window(cal, "2025-06-01", "2025-06-30")) == 30
    assert len(window(cal, end="2025-01-31")) == 31


def test_window_refused_on_table_without_gaming_date():
    with pytest.raises(ValueError):
        load("machines", start="2025-01-01")


def test_unknown_column_and_table_are_errors():
    with pytest.raises(KeyError):
        load("machine_day", columns=["not_a_column"])
    with pytest.raises(KeyError):
        load("not_a_table")


def test_money_columns_arrive_as_floats():
    pv = load("prepared_daily_view", columns=["coin_in_usd", "theo_usd"])
    assert pv.dtypes.eq("float64").all()


def test_sql_connection_sees_every_table():
    rows = con(include_outputs=False).sql("SELECT count(*) FROM machine_day").fetchall()[0][0]
    assert rows == 56_110  # raw view: unfiltered


# ---------- money helpers ----------

def test_cents_to_usd():
    assert cents_to_usd(12345) == 123.45
    assert cents_to_usd(pd.Series([100, 250])).tolist() == [1.0, 2.5]


def test_safe_ratio_returns_nan_on_zero_or_missing_denominator():
    assert np.isnan(safe_ratio(5, 0))
    assert safe_ratio(1, 4) == 0.25
    assert safe_ratio(pd.Series([1, 2, 3]), pd.Series([0, 4, np.nan])).tolist()[1:2] == [0.5]
    assert safe_ratio(pd.Series([1, 2, 3]), pd.Series([0, 4, np.nan])).isna().tolist() == [True, False, True]
    assert safe_ratio(pd.Series([1.0, 2.0]), 0).isna().all()


# ---------- gaming date ----------

def test_2am_local_belongs_to_previous_gaming_day():
    # Sat 2025-01-04 02:00 PST = 10:00 UTC -> Friday's gaming day
    assert to_gaming_date("2025-01-04 10:00:00") == pd.Timestamp("2025-01-03")
    # 06:00 PST = 14:00 UTC starts the new gaming day
    assert to_gaming_date("2025-01-04 13:59:59") == pd.Timestamp("2025-01-03")
    assert to_gaming_date("2025-01-04 14:00:00") == pd.Timestamp("2025-01-04")


def test_dst_day_boundaries():
    # Gaming date 2025-03-08 runs 14:00 UTC 3/8 -> 13:00 UTC 3/9 (23 hours)
    assert to_gaming_date("2025-03-09 12:59:59") == pd.Timestamp("2025-03-08")
    assert to_gaming_date("2025-03-09 13:00:00") == pd.Timestamp("2025-03-09")
    # Summer: 06:00 PDT = 13:00 UTC. Subtracting a fixed offset would get this wrong.
    assert to_gaming_date("2025-06-10 13:30:00") == pd.Timestamp("2025-06-10")


def test_tz_aware_input_and_out_of_window():
    local_2am = pd.Timestamp("2025-01-04 02:00", tz="America/Los_Angeles")
    assert to_gaming_date(local_2am) == pd.Timestamp("2025-01-03")
    assert pd.isna(to_gaming_date("2025-07-01 20:00:00"))


def test_series_input_keeps_index_and_matches_operations_rows():
    ops = load("operations", columns=["opened_at_utc", "opened_at_local"]).set_index(pd.RangeIndex(100, 1326))
    gd = to_gaming_date(ops["opened_at_utc"])
    assert gd.index.equals(ops.index)
    assert gd.notna().all()
    # Cross-check against the local clock: before 06:00 local belongs to the previous date.
    local = ops["opened_at_local"]
    expected = (local - pd.to_timedelta((local.dt.hour < 6).astype(int), unit="D")).dt.normalize()
    assert (gd == expected).all()


# ---------- shift ----------

def test_shift_boundaries():
    assert to_shift("2025-01-04 14:00:00") == "day"    # 06:00 PST
    assert to_shift("2025-01-04 21:59:59") == "day"    # 13:59 PST
    assert to_shift("2025-01-04 22:00:00") == "swing"  # 14:00 PST
    assert to_shift("2025-01-05 06:00:00") == "grave"  # 22:00 PST
    assert to_shift("2025-01-04 10:00:00") == "grave"  # 02:00 PST


def test_shift_on_dst_overlap_follows_gaming_date():
    # shift_roster lists the 3/8 grave shift until 14:00 UTC 3/9, but gaming date 3/9 (and its
    # day shift) starts at 13:00 UTC. The hour in between belongs to the 3/9 day shift.
    assert to_shift("2025-03-09 12:30:00") == "grave"
    assert to_shift("2025-03-09 13:30:00") == "day"


def test_every_repair_ticket_gets_a_shift():
    ops = load("operations", columns=["opened_at_utc", "opened_at_local"])
    shift = to_shift(ops["opened_at_utc"])
    assert shift.notna().all()
    hour = ops["opened_at_local"].dt.hour
    expected = np.select([(hour >= 6) & (hour < 14), (hour >= 14) & (hour < 22)], ["day", "swing"], "grave")
    assert (shift.to_numpy() == expected).all()
