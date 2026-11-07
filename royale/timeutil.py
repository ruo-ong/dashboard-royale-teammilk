"""Timestamp -> gaming date and timestamp -> shift.

Never subtract 6 hours by hand: the gaming day is 06:00-06:00 *local* time, its UTC start moves
with daylight saving (14:00 UTC in winter, 13:00 UTC in summer), and 2025-03-08 is 23 hours long.
These helpers look the answer up in calendar_day / shift_roster instead.

    from royale.timeutil import to_gaming_date, to_shift
    ops["gaming_date"] = to_gaming_date(ops["opened_at_utc"])
    ops["shift"] = to_shift(ops["opened_at_utc"])

Inputs are UTC timestamps: naive (assumed UTC, like every *_utc column) or tz-aware (converted).
Do not pass *_local columns.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from royale.data import load

_NS = "datetime64[ns]"


def _as_utc_series(ts) -> tuple[pd.Series, bool]:
    """Normalise input to a naive-UTC datetime64[ns] Series. Returns (series, input_was_scalar)."""
    scalar = pd.api.types.is_scalar(ts)
    s = pd.Series([ts]) if scalar else pd.Series(ts)
    s = pd.to_datetime(s)
    if s.dt.tz is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s.astype(_NS), scalar


@lru_cache(maxsize=1)
def _calendar() -> pd.DataFrame:
    cal = load("calendar_day", columns=["gaming_date", "gaming_day_start_utc", "gaming_day_end_utc"])
    cal["gaming_day_start_utc"] = cal["gaming_day_start_utc"].astype(_NS)
    cal["gaming_day_end_utc"] = cal["gaming_day_end_utc"].astype(_NS)
    cal["gaming_date"] = pd.to_datetime(cal["gaming_date"]).astype(_NS)
    return cal.sort_values("gaming_day_start_utc").reset_index(drop=True)


@lru_cache(maxsize=1)
def _shift_windows() -> pd.DataFrame:
    roster = load("shift_roster", columns=["gaming_date", "shift", "start_utc", "end_utc"])
    windows = roster.drop_duplicates().copy()
    if windows.duplicated(["gaming_date", "shift"]).any():
        raise RuntimeError("shift_roster has conflicting start/end times for the same gaming date and shift")
    windows["start_utc"] = windows["start_utc"].astype(_NS)
    windows["end_utc"] = windows["end_utc"].astype(_NS)
    windows["gaming_date"] = pd.to_datetime(windows["gaming_date"]).astype(_NS)
    return windows.sort_values("start_utc").reset_index(drop=True)


def _lookup_gaming_date(s: pd.Series) -> pd.Series:
    left = pd.DataFrame({"ts": s, "_order": range(len(s))}).dropna(subset=["ts"]).sort_values("ts")
    merged = pd.merge_asof(left, _calendar(), left_on="ts", right_on="gaming_day_start_utc", direction="backward")
    inside = merged["ts"] < merged["gaming_day_end_utc"]
    merged["gaming_date"] = merged["gaming_date"].where(inside)
    out = pd.Series(pd.NaT, index=range(len(s)), dtype=_NS)
    out.loc[merged["_order"].to_numpy()] = merged["gaming_date"].to_numpy()
    return out


def to_gaming_date(ts):
    """UTC timestamp(s) -> gaming date (Timestamp at midnight). NaT outside Jan 1-Jun 30 2025.

    Returns a scalar for scalar input, otherwise a Series aligned with the input's index.
    """
    s, scalar = _as_utc_series(ts)
    out = _lookup_gaming_date(s.reset_index(drop=True))
    if scalar:
        return out.iloc[0]
    out.index = s.index
    return out


def to_shift(ts):
    """UTC timestamp(s) -> 'day' | 'swing' | 'grave' (06-14, 14-22, 22-06 local), from shift_roster.

    The timestamp is placed in its gaming date first, then in that date's shift. This matters on the
    DST night: the 2025-03-08 grave shift is listed until 14:00 UTC on 3/9, but gaming date 3/9 starts
    at 13:00 UTC, so 13:00-14:00 UTC on 3/9 belongs to the 3/9 *day* shift.
    """
    s, scalar = _as_utc_series(ts)
    original_index = s.index
    s = s.reset_index(drop=True)
    gaming_date = _lookup_gaming_date(s)
    left = pd.DataFrame({"ts": s, "gaming_date": gaming_date, "_order": range(len(s))})
    left = left.dropna(subset=["ts", "gaming_date"]).sort_values("ts")
    merged = pd.merge_asof(
        left, _shift_windows(), left_on="ts", right_on="start_utc", by="gaming_date", direction="backward"
    )
    inside = merged["ts"] < merged["end_utc"]
    merged["shift"] = merged["shift"].where(inside)
    out = pd.Series(None, index=range(len(s)), dtype="object")
    out.loc[merged["_order"].to_numpy()] = merged["shift"].to_numpy()
    if scalar:
        value = out.iloc[0]
        return None if pd.isna(value) else value
    out.index = original_index
    return out
