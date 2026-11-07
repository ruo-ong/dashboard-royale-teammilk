"""Shared outputs folder. Every task writes exactly one named table here, and the dashboard reads only these.

Naming: task-ID prefix in lower case (a3_luck, b2_event_uplift, c3_downtime_cost ...).
The hand-off tables in the work plan keep their contract names (machine_day_base, machine_verdicts,
zone_day, closure_effect, tickets_clean, downtime_cost, player_totals, forecast_results, portfolio ...).
Rename only after telling the team, since other tasks read these names.

The outputs/ folder is gitignored: rebuild with the task scripts (see README).
"""
import os
import re
import threading

import pandas as pd

from royale.paths import OUTPUTS

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def output_path(name: str):
    if not _NAME.match(name):
        raise ValueError(f"Output names are lower_snake_case, e.g. 'a3_luck' (got {name!r})")
    return OUTPUTS / f"{name}.parquet"


def write_output(name: str, df: pd.DataFrame) -> None:
    """Write atomically: to a temporary file first, then swap it in, so a reader never sees a half-written table."""
    OUTPUTS.mkdir(exist_ok=True)
    path = output_path(name)
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def read_output(name: str) -> pd.DataFrame:
    path = output_path(name)
    if not path.exists():
        raise FileNotFoundError(f"{path.name} has not been built yet. Run the task that makes it (see README).")
    return pd.read_parquet(path)
