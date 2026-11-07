"""M6 - machine-level estimator: how much would a machine with these characteristics be expected to earn?

Run:  python -m tasks.m6_machine_model
  -> m6_validation        accuracy on May-June (fitted on Jan-Apr) vs simple benchmarks
  -> m6_test_predictions  per machine: predicted vs actual May-June earnings per available hour
  -> m6_coefficients      the fitted location (bank), game and manufacturer effects (refit on Jan-Jun)
  -> m6_games             per game: payback %, volatility, luck variance per dollar wagered
  -> m6_settings          intercept, uncertainty range, July demand factor, supplied cost rates

Model: log(expected win per available hour) = baseline + bank effect + game effect + manufacturer effect,
fitted by weighted least squares (weights = available hours) with a small ridge penalty so banks with few
machines are pulled toward the floor average. Validated with a time split, like the floor forecast (M1-M4).
The July demand factor comes from the existing floor forecast (m5_july_forecast).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import read_output, write_output

TRAIN = ("2025-01-01", "2025-04-30")
TEST = ("2025-05-01", "2025-06-30")
RIDGE = 1.0
MIN_TEST_DAYS = 20
MIN_OWN_HISTORY_DAYS = 30


def machine_table(base: pd.DataFrame) -> pd.DataFrame:
    """One row per machine for a period: its main bank (most available hours), game, maker, lease, results."""
    m = summarize(base, "machine_id")[["machine_id", "days_on_floor", "available_hours", "theo_usd", "coin_in_usd", "tpah", "availability"]]
    main_bank = (base.groupby(["machine_id", "bank_id"])["available_hours"].sum().reset_index()
                 .sort_values("available_hours", ascending=False).drop_duplicates("machine_id")[["machine_id", "bank_id"]])
    attrs = base.sort_values("gaming_date").groupby("machine_id")[["zone_id", "zone_name", "config_id", "theme", "manufacturer", "lease_class"]].last().reset_index()
    return m.merge(main_bank, on="machine_id").merge(attrs, on="machine_id")


class MachineModel:
    def fit(self, df: pd.DataFrame) -> "MachineModel":
        df = df[(df["tpah"] > 0) & (df["available_hours"] > 0)]
        self.banks = sorted(df["bank_id"].unique())
        self.configs = sorted(df["config_id"].unique())
        self.makers = sorted(df["manufacturer"].unique())
        X = self._design(df)
        y = np.log(df["tpah"].to_numpy())
        w = (df["available_hours"] / df["available_hours"].mean()).to_numpy()
        pen = np.full(X.shape[1], RIDGE)
        pen[0] = 0.0  # no penalty on the baseline
        A = X.T @ (X * w[:, None]) + np.diag(pen)
        self.beta = np.linalg.solve(A, X.T @ (w * y))
        resid = y - X @ self.beta
        self.smear = float(np.average(np.exp(resid), weights=w))
        return self

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.ones(len(df))]
        cols += [(df["bank_id"] == b).to_numpy(float) for b in self.banks]
        cols += [(df["config_id"] == c).to_numpy(float) for c in self.configs]
        cols += [(df["manufacturer"] == m).to_numpy(float) for m in self.makers]
        return np.column_stack(cols)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.exp(self._design(df) @ self.beta) * self.smear

    def coefficients(self) -> pd.DataFrame:
        names = [("baseline", "baseline")] + [("bank", b) for b in self.banks] + [("game", c) for c in self.configs] + [("manufacturer", m) for m in self.makers]
        out = pd.DataFrame(names, columns=["term_type", "term"])
        out["coef"] = self.beta
        out["multiplier"] = np.exp(out["coef"])
        return out


def validate() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    train = machine_table(load_base(*TRAIN))
    test = machine_table(load_base(*TEST))
    test = test[test["days_on_floor"] >= MIN_TEST_DAYS]
    model = MachineModel().fit(train)
    t = test.merge(train[["machine_id", "tpah", "days_on_floor"]].rename(columns={"tpah": "own_history_tpah", "days_on_floor": "own_days"}),
                   on="machine_id", how="left")
    t["model_tpah"] = model.predict(t)
    t["floor_median_tpah"] = train["tpah"].median()
    bank_avg = summarize(load_base(*TRAIN), "bank_id").set_index("bank_id")["tpah"]
    t["bank_average_tpah"] = t["bank_id"].map(bank_avg)
    rows = []
    for col, name, scope in [("model_tpah", "Estimator (location + game + manufacturer)", "all"),
                             ("bank_average_tpah", "Benchmark: average of the machine's bank", "all"),
                             ("floor_median_tpah", "Benchmark: floor median", "all"),
                             ("own_history_tpah", "Reference: the machine's own January-April result", "machines with history")]:
        s = t[t["own_days"] >= MIN_OWN_HISTORY_DAYS] if scope != "all" else t
        err = s[col] - s["tpah"]
        rows.append({"method": name, "machines": len(s), "mae_per_hour_usd": err.abs().mean(),
                     "mape": (err.abs() / s["tpah"]).mean(), "bias_per_hour_usd": err.mean(),
                     "mae_30_days_usd": err.abs().mean() * 24 * 30 * s["availability"].mean()})
    # Spread of the error around its typical value. The overall level shift between periods (May-June business
    # was lower) is handled separately by the July demand factor from the floor forecast, so it is not counted twice.
    log_ratio = np.log(t["tpah"] / t["model_tpah"])
    centred = log_ratio - log_ratio.median()
    q = {"q10": float(np.exp(centred.quantile(0.10))), "q90": float(np.exp(centred.quantile(0.90))),
         "level_shift": float(np.exp(log_ratio.median()))}
    centre = t["model_tpah"] * q["level_shift"]
    t["within_80pct_range"] = (t["tpah"] >= centre * q["q10"]) & (t["tpah"] <= centre * q["q90"])
    return pd.DataFrame(rows), t, q


def game_table(base: pd.DataFrame) -> pd.DataFrame:
    gm = load("game_math")
    g = base.groupby("config_id")[["luck_var_usd2", "coin_in_usd", "theo_usd", "available_hours"]].sum()
    g["luck_var_per_coin_in"] = g["luck_var_usd2"] / g["coin_in_usd"]
    g["floor_tpah"] = g["theo_usd"] / g["available_hours"]
    out = gm[["config_id", "theme", "configured_rtp", "volatility_class", "hit_probability"]].merge(
        g[["luck_var_per_coin_in", "floor_tpah"]].reset_index(), on="config_id")
    out["configured_rtp"] = out["configured_rtp"].astype(float)
    out["expected_hold"] = 1 - out["configured_rtp"]
    return out


def settings(base: pd.DataFrame, model: MachineModel, q: dict) -> pd.DataFrame:
    rules = load("cost_rules").set_index("cost_rule_id")
    rate = lambda rid: float(rules.loc[rid, "rate"])
    repair = base.groupby("manufacturer")["repair_cost_usd"].sum() / base.groupby("manufacturer").size()
    july = read_output("m5_july_forecast")["forecast_coin_in_usd"].mean()
    hist = load("property_day")["coin_in_usd"].astype(float).mean()
    row = {"smear": model.smear, "range_low_multiplier": q["q10"], "range_high_multiplier": q["q90"],
           "july_demand_factor": july / hist, "floor_median_tpah": summarize(base, "machine_id")["tpah"].median(),
           "median_availability": summarize(base, "machine_id")["availability"].median(),
           "lease_fixed_per_day_usd": rate("CR-LEASE-FIXED") / 100, "lease_share_of_positive_win": rate("CR-LEASE-SHARE"),
           "power_per_day_usd": rate("CR-POWER") / 100}
    for m in model.makers:
        rid = [r for r in rules.index if r.startswith("CR-SVC-") and rules.loc[r, "entity_id"] == m]
        row[f"service_per_day_usd__{m}"] = rate(rid[0]) / 100 if rid else 0.0
        row[f"repair_per_day_usd__{m}"] = float(repair.get(m, 0.0))
    return pd.DataFrame([row])


def estimate(game: str, bank_id: str, manufacturer: str, lease_class: str, availability: float, days: int,
             july_adjust: bool = True) -> dict:
    """Everything the estimator page shows, from the saved outputs. `game` is a config_id."""
    coef = read_output("m6_coefficients").set_index(["term_type", "term"])["coef"]
    s = read_output("m6_settings").iloc[0]
    games = read_output("m6_games").set_index("config_id")
    log_tpah = coef[("baseline", "baseline")] + coef.get(("bank", bank_id), 0.0) + coef.get(("game", game), 0.0) + coef.get(("manufacturer", manufacturer), 0.0)
    factor = s["july_demand_factor"] if july_adjust else 1.0
    tpah = float(np.exp(log_tpah) * s["smear"] * factor)
    hours = 24 * days * availability
    win = tpah * hours
    hold = games.loc[game, "expected_hold"]
    coin_in = win / hold
    luck_sd = float(np.sqrt(games.loc[game, "luck_var_per_coin_in"] * coin_in))
    lease = s["lease_fixed_per_day_usd"] * days if lease_class == "leased_fixed" else (
        s["lease_share_of_positive_win"] * win if lease_class == "leased_revenue_share" else 0.0)
    costs = {"lease": lease, "service": s[f"service_per_day_usd__{manufacturer}"] * days,
             "power": s["power_per_day_usd"] * days, "repairs": s[f"repair_per_day_usd__{manufacturer}"] * days}
    return {"tpah": tpah, "tpah_low": tpah * s["range_low_multiplier"], "tpah_high": tpah * s["range_high_multiplier"],
            "available_hours": hours, "expected_win": win, "expected_win_low": win * s["range_low_multiplier"],
            "expected_win_high": win * s["range_high_multiplier"], "coin_in": coin_in, "luck_sd": luck_sd,
            "house_win_low": win - 2 * luck_sd, "house_win_high": win + 2 * luck_sd, "costs": costs,
            "total_costs": sum(costs.values()), "contribution": win - sum(costs.values()), "demand_factor": factor,
            "hold": hold, "floor_median_tpah": s["floor_median_tpah"] * factor}


def main() -> None:
    validation, preds, q = validate()
    write_output("m6_validation", validation)
    write_output("m6_test_predictions", preds)
    base = load_base()
    full = MachineModel().fit(machine_table(base))
    write_output("m6_coefficients", full.coefficients())
    write_output("m6_games", game_table(base))
    write_output("m6_settings", settings(base, full, q))
    print("M6 validation on May-June (fitted on Jan-Apr):")
    print(validation.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    print(f"80% range: x{q['q10']:.2f} to x{q['q90']:.2f} (level shift May-June x{q['level_shift']:.3f}); actual inside for "
          f"{preds['within_80pct_range'].mean():.0%} of {len(preds)} test machines")
    e = estimate("G-STD90", "B-12", "Northwind", "owned", 0.997, 30)
    print(f"Example: Desert Gold, bank B-12, Northwind, owned, 30 days -> ${e['tpah']:.2f}/h, expected win ${e['expected_win']:,.0f} "
          f"(${e['expected_win_low']:,.0f}-${e['expected_win_high']:,.0f}), contribution ${e['contribution']:,.0f}")


if __name__ == "__main__":
    main()
