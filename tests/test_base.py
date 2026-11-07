"""F4 checks on outputs/machine_day_base.parquet and the shared metrics. Builds the table if it is missing."""
import duckdb
import numpy as np
import pandas as pd
import pytest

from royale.data import window
from royale.metrics import summarize
from royale.outputs import output_path, read_output
from royale.paths import table_path


@pytest.fixture(scope="module")
def base():
    if not output_path("machine_day_base").exists():
        from tasks.f4_machine_day_base import main
        main()
    return read_output("machine_day_base")


def test_reconciliation_passes():
    from tasks.f4_machine_day_base import build, reconcile
    failed = [(name, detail) for name, passed, detail in reconcile(build()) if not passed]
    assert failed == []


def test_shape_and_on_floor_only(base):
    assert len(base) == 55_092
    assert base["on_floor_hours"].gt(0).all()


def test_bottom_10_matches_the_guide_query(base):
    ours = summarize(base, "machine_id").nsmallest(10, "house_win_usd")["machine_id"].tolist()
    guide = duckdb.sql(f"""
        SELECT machine_id FROM read_parquet('{table_path("prepared_daily_view")}')
        WHERE active GROUP BY machine_id ORDER BY SUM(house_win_usd) LIMIT 10
    """).df()["machine_id"].tolist()
    assert ours == guide


def test_luck_z_looks_like_a_bell_curve(base):
    # Plan A3 sanity check: centred near 0, roughly 5% beyond +-2. If not, the variance units are wrong.
    z = summarize(base, "machine_id")["luck_z"]
    assert abs(z.mean()) < 0.25
    assert 0.7 < z.std() < 1.4
    assert 0.01 < (z.abs() > 2).mean() < 0.12


def test_summarize_is_ratio_of_sums_for_any_window(base):
    q1 = window(base, "2025-01-01", "2025-03-31")
    floor = summarize(q1).iloc[0]
    assert floor["tpah"] == pytest.approx(q1["theo_usd"].sum() / q1["available_hours"].sum())
    assert floor["observed_hold"] == pytest.approx(q1["house_win_usd"].sum() / q1["coin_in_usd"].sum())
    assert floor["luck_sd_usd"] == pytest.approx(np.sqrt(q1["luck_var_usd2"].sum()))


def test_summarize_groups_add_up_to_floor(base):
    by_zone = summarize(base, "zone_id")
    floor = summarize(base).iloc[0]
    assert by_zone["theo_usd"].sum() == pytest.approx(floor["theo_usd"])
    assert by_zone["days_on_floor"].sum() == len(base)


def test_zero_coin_in_gives_null_hold():
    day = pd.DataFrame({"machine_id": ["X"], "coin_in_usd": [0.0], "house_win_usd": [0.0], "theo_usd": [0.0],
                        "available_hours": [24.0], "on_floor_hours": [24.0], "occupied_hours": [0.0],
                        "luck_residual_usd": [0.0], "luck_var_usd2": [0.0], "paid_spins": [0],
                        "payout_positive_spins": [0], "expected_hits": [0.0], "hit_var": [0.0]})
    row = summarize(day).iloc[0]
    assert np.isnan(row["observed_hold"]) and np.isnan(row["luck_z"]) and row["tpah"] == 0
