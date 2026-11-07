"""Invariant checks for workstreams B, C, D, E, M, R and A9 on the built outputs."""
import numpy as np
import pandas as pd
import pytest

from royale.data import load
from royale.outputs import output_path, read_output


@pytest.fixture(scope="module", autouse=True)
def built():
    if not output_path("portfolio").exists():
        from tasks.run_all import run
        run()


# ---------- B ----------
def test_floor_trend_matches_property_day():
    d = read_output("b1_floor_trend")
    assert d["coin_in_usd"].sum() == pytest.approx(load("property_day")["coin_in_usd"].astype(float).sum())


def test_zone_day_adds_up_to_floor():
    z = read_output("zone_day")
    assert z["theo_usd"].sum() == pytest.approx(read_output("machine_day_base")["theo_usd"].sum())
    assert np.allclose(z.groupby("gaming_date")["share_of_floor_theo"].sum(), 1.0)


def test_closure_affects_back_forty_only():
    c = read_output("closure_effect")
    assert c["affected_zones"].iloc[0] == "Z-B40"
    assert c["theo_lost_low_usd"].iloc[0] <= c["theo_lost_usd"].iloc[0] <= c["theo_lost_high_usd"].iloc[0]
    assert pd.Timestamp(c["closed_from"].iloc[0]) == pd.Timestamp("2025-03-03")
    assert pd.Timestamp(c["closed_through"].iloc[0]) == pd.Timestamp("2025-04-06")


def test_traffic_offline_is_missing_not_zero():
    t = read_output("b5_traffic_daily")
    raw = load("zone_traffic_hourly")
    assert raw.loc[raw["counter_status"] == "offline", "entries_count"].isna().all()
    assert (t["coverage_share"] <= 1.0 + 1e-9).all()


def test_event_ranges_bracket_the_estimate():
    e = read_output("b2_event_uplift")
    assert ((e["uplift_low_usd"] <= e["uplift_usd"]) & (e["uplift_usd"] <= e["uplift_high_usd"])).all()


def test_story_claims_are_logged():
    log = pd.read_csv("docs/claims_log.csv")
    assert set(read_output("b9_story")["claim_id"]) <= set(log["claim_id"])


# ---------- C ----------
def test_downtime_reconciles_three_ways():
    t = read_output("c2_downtime_totals").iloc[0]
    assert t["meter_down_hours"] == pytest.approx(t["ticket_hours"], abs=0.01)
    assert t["meter_down_hours"] == pytest.approx(t["down_hours_matched_to_ticket"], abs=0.01)


def test_tickets_have_no_negative_stage_when_measured_from_opened():
    t = read_output("tickets_clean")
    assert (t[["response_h", "repair_h", "total_h"]] >= 0).all().all()
    assert t["shift"].notna().all() and t["gaming_date"].notna().all()


def test_lost_theo_range_and_index():
    c = read_output("downtime_cost")
    assert (c["lost_theo_low_usd"] <= c["lost_theo_usd"] + 1e-9).all() and (c["lost_theo_usd"] <= c["lost_theo_high_usd"] + 1e-9).all()
    h = read_output("c3_hour_of_week")
    weighted = (h["index"] * h["available_hours"]).sum() / h["available_hours"].sum()
    assert weighted == pytest.approx(1.0)


def test_reliability_intervals_contain_the_rate():
    r = read_output("manufacturer_reliability")
    assert ((r["faults_per_1000h_low"] < r["faults_per_1000h"]) & (r["faults_per_1000h"] < r["faults_per_1000h_high"])).all()


# ---------- A9 ----------
def test_every_machine_has_one_verdict():
    v = read_output("machine_verdicts")
    assert len(v) == v["machine_id"].nunique() == 310
    assert v.set_index("machine_id").loc["M-1158", "verdict"] == "Inspect"
    assert (v.loc[v["on_our_list"], "verdict"] == "Truly weak").all()
    assert set(read_output("a9_list_comparison")["status"]) <= {"stays", "review", "drops", "new"}


# ---------- D ----------
def test_player_totals_reconcile():
    pt = read_output("player_totals")
    pp = load("player_period")
    for col in ["tracked_coin_in_usd", "tracked_net_usd", "theo_usd", "comp_cost_usd"]:
        assert pt[col].sum() == pytest.approx(pp[col].astype(float).sum())
    assert (pt["age_band"].notna()).all()  # missing age band is its own group


def test_concentration_is_monotone():
    c = read_output("d3_concentration")
    for _, g in c.groupby("measure"):
        assert g.sort_values("top_share_of_players")["share_of_total"].is_monotonic_increasing
    lor = read_output("d3_lorenz")
    assert (lor["share_of_total"] <= lor["share_of_players"] + 1e-9).all()


# ---------- E ----------
def test_comp_cost_reconciles():
    s = read_output("e1_comp_series")
    assert s["ledger_cost_usd"].sum() == pytest.approx(s["comp_cost_usd"].sum())


def test_comp_change_found():
    c = read_output("e3_change").iloc[0]
    assert pd.Timestamp(c["change_date"]) == pd.Timestamp("2025-05-01")
    assert c["change_pct"] < -0.4
    assert read_output("e4_change_impact")["verdict"].iloc[0] in {"paid for itself", "did not pay for itself", "can't tell yet"}


# ---------- M ----------
def test_model_never_sees_the_future():
    from tasks.m_model import AS_OF, features
    dates = pd.Series(pd.date_range("2025-06-09", "2025-06-15"))
    X = features(dates, pd.Series([None] * 7), AS_OF)
    assert X["property_promotion"].sum() == 0          # Locals Week was announced May 26: unknown on April 30
    r = read_output("forecast_results")
    assert r["gaming_date"].min() == pd.Timestamp("2025-05-01") and r["gaming_date"].max() == pd.Timestamp("2025-06-30")
    assert read_output("m3_selection")["chosen"].sum() == 1


def test_model_beats_constant_baseline():
    m = read_output("m4_metrics")
    allm = m[m["scope"] == "all test days"].set_index("model")["mae_usd"]
    chosen = allm[allm.index.str.contains(r"\[chosen\]")].iloc[0]
    assert chosen < allm[allm.index.str.startswith("Baseline A")].iloc[0]


# ---------- R ----------
def test_costs_follow_the_guide():
    c = read_output("r1_costs")
    assert c.query("action_type_id == 'A-REPLACE-LEASE' and quantity == 1")["cost_usd"].iloc[0] == pytest.approx(3380)


def test_portfolio_respects_budget_and_rules():
    p = read_output("portfolio")
    funded = p[p["action_type_id"] != "A-HOLD"]
    assert funded["cost"].sum() <= 100_000
    assert funded["action_type_id"].nunique() <= 3
    limits = load("action_catalog").set_index("action_type_id")["quantity_limit"]
    assert (funded["quantity"] <= funded["action_type_id"].map(limits)).all()
    assert not {"A-COMP-PILOT", "A-COMP-CHANGE"} <= set(funded["action_type_id"])
    assert funded["claim_ids"].str.len().gt(0).all()       # every action points to evidence
    assert p.loc[p["action_type_id"] == "A-HOLD", "kept_usd"].iloc[0] == pytest.approx(100_000 - funded["cost"].sum())


def test_every_funded_action_has_a_measurement_plan():
    p = read_output("portfolio")
    m = read_output("r6_measurement").set_index("action_type_id")
    for a in p.loc[p["action_type_id"] != "A-HOLD", "action_type_id"]:
        assert m.loc[a, ["metric", "comparison", "check_date", "success", "if_fails"]].notna().all()


def test_plan_claim_ids_exist():
    log = set(pd.read_csv("docs/claims_log.csv")["claim_id"])
    cited = {c.strip() for ids in read_output("r3_benefits")["claim_ids"] for c in ids.split(",")}
    assert cited <= log, cited - log


# ---------- M6 machine estimator ----------
def test_machine_estimator_beats_benchmarks():
    v = read_output("m6_validation").set_index("method")
    est = v[v.index.str.startswith("Estimator")]["mae_per_hour_usd"].iloc[0]
    assert est < v[v.index.str.contains("bank")]["mae_per_hour_usd"].iloc[0]
    assert est < v[v.index.str.contains("floor median")]["mae_per_hour_usd"].iloc[0]
    assert 0.7 <= read_output("m6_test_predictions")["within_80pct_range"].mean() <= 0.9


def test_estimate_is_consistent():
    from tasks.m6_machine_model import estimate
    a = estimate("G-STD90", "B-12", "Northwind", "owned", 0.997, 30, july_adjust=False)
    b = estimate("G-STD90", "B-12", "Northwind", "owned", 0.997, 60, july_adjust=False)
    assert b["expected_win"] == pytest.approx(2 * a["expected_win"])          # linear in days
    assert a["tpah_low"] < a["tpah"] < a["tpah_high"]
    assert a["house_win_low"] < a["expected_win"] < a["house_win_high"]
    assert a["contribution"] == pytest.approx(a["expected_win"] - a["total_costs"])
    fixed = estimate("G-STD90", "B-12", "Northwind", "leased_fixed", 0.997, 30, july_adjust=False)
    assert fixed["costs"]["lease"] == pytest.approx(45 * 30)                  # cost_rules: $45 per active day
    weak = estimate("G-STD90", "B-38", "Northwind", "owned", 0.997, 30, july_adjust=False)
    assert weak["tpah"] < a["tpah"]                                            # Back Forty bank earns less than Center Pit


# ---------- fixes from the external review ----------
def test_borderline_verdict_is_stable_across_periods():
    from royale.data import load_base
    from tasks import a9_verdicts
    from tasks.a1_manager_list import manager_ten
    full = read_output("machine_verdicts").set_index("machine_id")
    q2 = a9_verdicts.compute(load_base("2025-04-01", "2025-06-30"), "2025-04-01", "2025-06-30", read_output("c7_chronic"),
                             {"Z-B40"}, manager_ten()).set_index("machine_id")
    assert full.loc["M-1179", "verdict"] == q2.loc["M-1179", "verdict"] == "Borderline"


def test_one_promotion_weekend_with_a_comparison_weekend():
    p = read_output("portfolio").set_index("action_type_id")
    assert p.loc["A-PROMO", "quantity"] == 1
    d = read_output("m5_decision")
    chosen, comparison = d[d["chosen"]], d[d["comparison"]]
    assert len(chosen) == 1 and len(comparison) == 1
    assert comparison["friday"].iloc[0] > chosen["friday"].iloc[0]


def test_points_liability_is_consistent():
    L = read_output("e3_points_liability").iloc[0]
    assert L["points_outstanding"] == pytest.approx(L["points_awarded"] - L["points_redeemed"])
    assert L["cost_if_all_redeemed_after_usd"] > L["cost_if_all_redeemed_before_usd"]
    assert L["extra_cost_if_all_redeemed_usd"] == pytest.approx(L["cost_if_all_redeemed_after_usd"] - L["cost_if_all_redeemed_before_usd"])
    assert 0 < L["extra_cost_at_observed_redemption_usd"] < L["extra_cost_if_all_redeemed_usd"]


def test_comet_cash_is_played_less_in_both_halves():
    g = read_output("a9_game_review").set_index("theme")
    assert g.loc["Comet Cash", "played_less_in_both_halves"]
    assert set(g.index[g["played_less_in_both_halves"]]) == {"Comet Cash"}
