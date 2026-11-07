"""Checks for A1 (manager list), A2 (exposure), A3 (luck) and A5 (location)."""
import numpy as np
import pandas as pd
import pytest

from royale.data import load_base
from royale.metrics import summarize
from royale.outputs import output_path
from tasks import a1_manager_list, a2_exposure, a3_luck, a4_leak, a5_location, a6_moves, a8_decomposition, a11_profit


@pytest.fixture(scope="module")
def base():
    if not output_path("machine_day_base").exists():
        from tasks.f4_machine_day_base import main
        main()
    return load_base("2025-01-01", "2025-06-30")


@pytest.fixture(scope="module")
def ten(base):
    return a1_manager_list.manager_ten(base)


@pytest.fixture(scope="module")
def exposure(base, ten):
    return a2_exposure.compute(base, "2025-01-01", "2025-06-30", ten)


@pytest.fixture(scope="module")
def luck(base, ten):
    return a3_luck.compute(base, ten)


@pytest.fixture(scope="module")
def location(base, ten):
    return a5_location.compute(base, ten)


# ---------- A1 ----------

def test_manager_list(base, ten):
    out = a1_manager_list.compute(base)
    assert len(out) == 25 and out["in_manager_10"].sum() == 10
    assert out["house_win_usd"].is_monotonic_increasing
    assert ten == out["machine_id"].head(10).tolist()


# ---------- A2 ----------

def test_exposure_ranks_and_metrics(base, exposure):
    n = len(exposure)
    assert sorted(exposure["rank_tpah"]) == list(range(1, n + 1))
    assert sorted(exposure["rank_house_win"]) == list(range(1, n + 1))
    ref = summarize(base, "machine_id").set_index("machine_id")["tpah"]
    assert np.allclose(exposure.set_index("machine_id")["tpah"], ref.reindex(exposure["machine_id"]))


def test_exposure_flags(exposure):
    assert exposure["window_days"].eq(181).all()
    assert exposure["partial_window"].sum() == (exposure["days_on_floor"] < 181).sum() == 12
    assert set(exposure.loc[exposure["low_evidence"], "machine_id"]) == {"M-5076", "M-1118"}


def test_every_manager_machine_has_a_rank_note(exposure):
    notes = exposure.loc[exposure["in_manager_10"], "rank_note"]
    assert len(notes) == 10 and notes.str.startswith("House-win rank").all()
    assert (exposure.loc[~exposure["in_manager_10"], "rank_note"] == "").all()


def test_exposure_respects_the_window(base, ten):
    q2 = a2_exposure.compute(load_base("2025-04-01", "2025-06-30"), "2025-04-01", "2025-06-30", ten)
    assert q2["window_days"].iloc[0] == 91
    assert q2["days_on_floor"].max() == 91


# ---------- A3 ----------

def test_luck_matches_shared_metrics(base, luck):
    machines, _ = luck
    ref = summarize(base, "machine_id").set_index("machine_id")
    got = machines.set_index("machine_id")
    assert np.allclose(got["luck_z"], ref.loc[got.index, "luck_z"])


def test_biggest_day_is_in_the_direction_of_the_total(luck):
    machines, _ = luck
    same_sign = np.sign(machines["biggest_day_residual_usd"]) == np.sign(machines["luck_residual_usd"])
    assert same_sign.all()


def test_luck_without_biggest_day_by_hand(base, luck):
    machines, _ = luck
    row = machines.set_index("machine_id").loc["M-1158"]
    days = base[base["machine_id"] == "M-1158"].set_index("gaming_date")
    rest = days.drop(index=row["biggest_day"])
    expected = rest["luck_residual_usd"].sum() / np.sqrt(rest["luck_var_usd2"].sum())
    assert row["luck_z_ex_biggest_day"] == pytest.approx(expected)


def test_monthly_luck_adds_up(luck):
    machines, months = luck
    total = months.groupby("machine_id")["luck_residual_usd"].sum()
    assert np.allclose(total.reindex(machines["machine_id"]), machines["luck_residual_usd"])
    assert (machines["months_negative"] <= machines["months_on_floor"]).all()


# ---------- A5 ----------

def test_peer_index_by_hand_for_one_machine(base, location):
    loc, _, _ = location
    row = loc.set_index("machine_id").loc["M-1035"]
    mine = base[base["machine_id"] == "M-1035"]
    days = set(mine["gaming_date"])
    peers = base[(base["bank_id"] == row["bank_id"]) & base["gaming_date"].isin(days) & (base["machine_id"] != "M-1035")]
    by_peer = peers.groupby("machine_id")[["theo_usd", "available_hours"]].sum()
    median_peer = (by_peer["theo_usd"] / by_peer["available_hours"]).median()
    assert row["bank_peer_tpah"] == pytest.approx(median_peer)
    assert row["peer_index"] == pytest.approx(row["tpah"] / median_peer)


def test_moved_machine_peer_tpah_is_days_weighted(base, location):
    loc, _, _ = location
    stints = a5_location.peer_medians(base)
    moved = stints[stints["machine_id"] == "M-1299"]
    assert len(moved) == 2
    expected = (moved["days_in_bank"] * moved["peer_median_tpah"]).sum() / moved["days_in_bank"].sum()
    assert loc.set_index("machine_id").loc["M-1299", "bank_peer_tpah"] == pytest.approx(expected)


def test_bank_scores(base, location):
    _, banks, _ = location
    assert len(banks) == 51 and banks["x_m"].notna().all()
    assert banks["bank_quartile"].value_counts().min() >= 12
    assert banks["theo_usd"].sum() == pytest.approx(base["theo_usd"].sum())


def test_game_by_zone_adds_up(base, location):
    _, _, games = location
    assert games["theo_usd"].sum() == pytest.approx(base["theo_usd"].sum())


def test_location_reads_are_consistent(location):
    loc, _, _ = location
    assert (loc.loc[loc["low_hold_game"], "machine_flag"]).all()
    assert set(loc["location_read"]) <= {"", "machine", "low-hold game", "location"}
    assert (loc.loc[loc["location_read"] == "machine", "volume_peer_index"] < 1 - a5_location.PEER_BAND).all()


# ---------- A4 ----------

@pytest.fixture(scope="module")
def leak(base, ten):
    return a4_leak.compute(base, ten)


def test_leak_flags_and_wording(leak):
    machines, _ = leak
    assert set(machines.loc[machines["hit_flag"], "machine_id"]) == {"M-1158"}
    assert "M-1158" in set(machines.loc[machines["inspection_lead"], "machine_id"])
    reasons = machines.loc[machines["inspection_lead"], "reason"]
    assert reasons.str.startswith("Inspect:").all()
    assert not reasons.str.contains("fraud|cheat", case=False).any()
    assert (machines.loc[~machines["inspection_lead"], "reason"] == "").all()


def test_ticket_change_scores_are_calibrated(leak):
    _, tickets = leak
    assert tickets["n_days_before"].max() <= a4_leak.TICKET_WINDOW_DAYS
    assert tickets["n_days_after"].max() <= a4_leak.TICKET_WINDOW_DAYS
    for col in ["hit_change_z", "hold_change_z"]:  # most tickets change nothing: z should look ~N(0,1)
        assert 0.8 < tickets[col].std() < 1.3


def test_ticket_window_by_hand(base, leak):
    _, tickets = leak
    t = tickets[tickets["machine_id"] == "M-1158"].iloc[0]
    days = base[base["machine_id"] == "M-1158"]
    before = days[(days["gaming_date"] < t["ticket_date"])
                  & (days["gaming_date"] >= t["ticket_date"] - pd.Timedelta(days=a4_leak.TICKET_WINDOW_DAYS))]
    assert t["n_days_before"] == len(before)
    assert t["hit_rate_before"] == pytest.approx(before["payout_positive_spins"].sum() / before["paid_spins"].sum())


# ---------- A6 ----------

def test_moves(base):
    moves = a6_moves.compute(base)
    assert len(moves) == 4
    assert (moves["days_before"] == a6_moves.WINDOW_DAYS).all()
    assert (moves["days_after"] <= a6_moves.WINDOW_DAYS).all()      # move day itself is skipped
    assert moves.set_index("machine_id").loc["M-1299", "days_after"] == 20  # moved Jun 10, window ends Jun 30
    net = (moves["tpah_after"] - moves["tpah_before"]) - moves["floor_tpah_change"]
    assert np.allclose(net, moves["tpah_effect"])
    assert (moves["origin_bank"] != moves["destination_bank"]).all()


# ---------- A8 ----------

@pytest.fixture(scope="module")
def decomposition(base, ten, location):
    return a8_decomposition.compute(base, "2025-01-01", "2025-06-30", ten, location[0])


def test_pieces_add_up_exactly(decomposition):
    pieces = [c for c, _, _ in a8_decomposition.PIECES]
    assert (decomposition[pieces].sum(axis=1) - decomposition["gap_usd"]).abs().max() < 0.01


def test_machine_piece_split_is_exact(decomposition):
    d = decomposition
    plan_piece = d["available_hours"] * (d["tpah"] - d["bank_peer_tpah"])
    assert np.allclose(d["machine_volume_usd"] + d["machine_hold_usd"], plan_piece)
    assert np.allclose(d["machine_itself_usd"], plan_piece)


def test_typical_machine_and_long_format(decomposition):
    d = decomposition
    assert d["full_window_hours"].iloc[0] == pytest.approx(181 * 24 - 1)  # one 23-hour DST day
    long = a8_decomposition.to_long(d)
    assert len(long) == len(d) * len(a8_decomposition.PIECES)
    assert long.groupby("machine_id")["usd"].sum().sub(long.groupby("machine_id")["gap_usd"].first()).abs().max() < 0.01


# ---------- A11 ----------

def test_profit(base):
    p = a11_profit.compute(base)
    assert p["contribution_usd"].sum() == pytest.approx(base["contribution_usd"].sum())
    assert np.allclose(p["expected_contribution_usd"], p["theo_usd"] - p["supplied_costs_usd"])
    assert not p.loc[~p["leased"], "lease_exceeds_theo"].any()
