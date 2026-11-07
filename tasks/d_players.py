"""Workstream D (Q4) - what did TRACKED players wager, get back and net, and how concentrated is it?

Run:  python -m tasks.d_players [--start 2025-01-01 --end 2025-06-30]   (months in the window)
  D1 player_totals          one row per tracked player: sums over the chosen months + attributes
  D2 d2_overview, d2_net_hist   headline numbers; distribution of net results
  D3 d3_concentration, d3_lorenz   top 1/5/10/20% shares and Gini for theo, coin-in, losses; Lorenz points
  D4 d4_luck_players        coin-in deciles: share ahead, actual net vs expected (-theo)
  D5 d5_segments            age band / region / opening tier / end tier comparison (the guest-group drill-down)
  D6 d6_monthly             active, new, returning, not seen again, tier upgrades by month
  D7 d7_protective          aggregate profile of the heaviest losers and longest sessions (no individual targeting)

Everything here is loyalty-card play only: always label it "tracked".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import load, load_base
from royale.outputs import write_output
from royale.util import safe_ratio

SUM_COLS = ["observed_visits", "incomplete_visits", "sessions", "carded_play_hours", "tracked_coin_in_usd",
            "tracked_payout_usd", "tracked_net_usd", "theo_usd", "luck_residual_usd", "linked_pos_cash_usd",
            "linked_pos_cogs_usd", "comps_redeemed", "comp_face_value_usd", "comp_cost_usd", "points_earned",
            "points_redeemed", "tracked_contribution_usd"]
TIER_ORDER = {"Base": 0, "Gold": 1, "Platinum": 2}


def months_in(start, end) -> list[str]:
    return [m.strftime("%Y-%m") for m in pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")]


def player_totals(months: list[str] | None = None) -> pd.DataFrame:
    pp = load("player_period")
    if months:
        pp = pp[pp["period_month"].isin(months)]
    pp = pp.sort_values("period_month")
    totals = pp.groupby("player_id")[SUM_COLS].sum()
    totals["months_active"] = pp.groupby("player_id").size()
    totals["first_month"] = pp.groupby("player_id")["period_month"].min()
    totals["last_month"] = pp.groupby("player_id")["period_month"].max()
    totals["tier_end"] = pp.groupby("player_id")["tier_end"].last()
    players = load("players", columns=["player_id", "enrolled_at_utc", "home_region", "age_band", "opening_tier"])
    out = totals.reset_index().merge(players, on="player_id", how="left")
    out["age_band"] = out["age_band"].fillna("Unknown")
    out["ahead"] = out["tracked_net_usd"] > 0
    out["gamed"] = out["tracked_coin_in_usd"] > 0
    return out


def overview(pt: pd.DataFrame, base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = pt[pt["gamed"]]
    o = {"tracked_players": len(pt), "players_with_carded_play": len(g),
         "tracked_coin_in_usd": g["tracked_coin_in_usd"].sum(), "tracked_payout_usd": g["tracked_payout_usd"].sum(),
         "tracked_net_usd": g["tracked_net_usd"].sum(), "tracked_theo_usd": g["theo_usd"].sum(),
         "tracked_share_of_all_coin_in": base["carded_coin_in_usd"].sum() / base["coin_in_usd"].sum(),
         "share_players_ahead": g["ahead"].mean(), "median_net_usd": g["tracked_net_usd"].median(),
         "mean_net_usd": g["tracked_net_usd"].mean(),
         "tracked_hold": -g["tracked_net_usd"].sum() / g["tracked_coin_in_usd"].sum()}
    edges = [-np.inf, -5000, -1000, -500, -250, -100, -50, -10, 0, 10, 50, 100, 250, 500, 1000, 5000, np.inf]
    labels = ["< -$5k", "-$5k to -$1k", "-$1k to -$500", "-$500 to -$250", "-$250 to -$100", "-$100 to -$50",
              "-$50 to -$10", "-$10 to $0", "$0 to $10", "$10 to $50", "$50 to $100", "$100 to $250", "$250 to $500",
              "$500 to $1k", "$1k to $5k", "> $5k"]
    bins = pd.cut(g["tracked_net_usd"], edges, labels=labels, right=False)
    hist = bins.value_counts().reindex(labels).rename_axis("net_band").reset_index(name="players")
    hist["order"] = range(len(hist))
    return pd.DataFrame([o]), hist


def _lorenz(values: np.ndarray) -> tuple[np.ndarray, float]:
    v = np.sort(np.clip(values, 0, None))
    cum = np.concatenate([[0], np.cumsum(v)]) / v.sum()
    n = len(v)
    gini = 1 - 2 * np.trapezoid(cum, dx=1 / n)
    return cum, gini


def concentration(pt: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = pt[pt["gamed"]]
    series = {"theo": g["theo_usd"].to_numpy(), "coin_in": g["tracked_coin_in_usd"].to_numpy(),
              "net_loss (losing players)": (-g.loc[~g["ahead"], "tracked_net_usd"]).to_numpy()}
    rows, curves = [], []
    for name, values in series.items():
        cum, gini = _lorenz(values)
        desc = np.sort(values)[::-1]
        total = desc.sum()
        for top in [0.01, 0.05, 0.10, 0.20]:
            k = max(1, int(round(top * len(desc))))
            rows.append({"measure": name, "top_share_of_players": top, "share_of_total": desc[:k].sum() / total,
                         "gini": gini, "players": len(desc)})
        pts = np.linspace(0, 1, 101)
        idx = np.round(pts * (len(cum) - 1)).astype(int)
        curves.append(pd.DataFrame({"measure": name, "share_of_players": pts, "share_of_total": cum[idx]}))
    return pd.DataFrame(rows), pd.concat(curves, ignore_index=True)


def luck_by_decile(pt: pd.DataFrame) -> pd.DataFrame:
    g = pt[pt["gamed"]].copy()
    g["decile"] = pd.qcut(g["tracked_coin_in_usd"].rank(method="first"), 10, labels=range(1, 11)).astype(int)
    d = g.groupby("decile").agg(players=("player_id", "size"), coin_in_min=("tracked_coin_in_usd", "min"),
                                coin_in_max=("tracked_coin_in_usd", "max"), share_ahead=("ahead", "mean"),
                                net_usd=("tracked_net_usd", "sum"), theo_usd=("theo_usd", "sum"),
                                median_net_usd=("tracked_net_usd", "median")).reset_index()
    d["expected_net_usd"] = -d["theo_usd"]
    d["net_per_player_usd"] = d["net_usd"] / d["players"]
    d["expected_net_per_player_usd"] = d["expected_net_usd"] / d["players"]
    return d


def segments(pt: pd.DataFrame) -> pd.DataFrame:
    g = pt[pt["gamed"]]
    rows = []
    for dim in ["age_band", "home_region", "opening_tier", "tier_end"]:
        for key, s in g.groupby(dim):
            rows.append({"dimension": dim, "segment": key, "players": len(s),
                         "coin_in_per_player_usd": s["tracked_coin_in_usd"].mean(),
                         "net_per_player_usd": s["tracked_net_usd"].mean(),
                         "theo_per_player_usd": s["theo_usd"].mean(),
                         "hold": -s["tracked_net_usd"].sum() / s["tracked_coin_in_usd"].sum(),
                         "share_ahead": s["ahead"].mean(), "visits_per_player": s["observed_visits"].mean(),
                         "hours_per_player": s["carded_play_hours"].mean(),
                         "comp_cost_per_player_usd": s["comp_cost_usd"].mean(),
                         "share_of_tracked_theo": s["theo_usd"].sum() / g["theo_usd"].sum()})
    return pd.DataFrame(rows)


def monthly(months: list[str]) -> pd.DataFrame:
    pp = load("player_period", columns=["player_id", "period_month", "opening_tier", "tier_end", "sessions",
                                        "observed_visits", "theo_usd"])
    pp = pp[pp["period_month"].isin(months)].sort_values(["player_id", "period_month"])
    pp["prev_tier"] = pp.groupby("player_id")["tier_end"].shift().fillna(pp["opening_tier"])
    pp["upgrade"] = pp["tier_end"].map(TIER_ORDER) > pp["prev_tier"].map(TIER_ORDER)
    first = pp.groupby("player_id")["period_month"].transform("min")
    last = pp.groupby("player_id")["period_month"].transform("max")
    pp["new"] = pp["period_month"] == first
    pp["not_seen_again"] = (pp["period_month"] == last) & (pp["period_month"] != months[-1])
    out = pp.groupby("period_month").agg(active_players=("player_id", "nunique"), new_players=("new", "sum"),
                                         not_seen_again=("not_seen_again", "sum"), tier_upgrades=("upgrade", "sum"),
                                         visits=("observed_visits", "sum"), theo_usd=("theo_usd", "sum")).reset_index()
    out["returning_players"] = out["active_players"] - out["new_players"]
    out["theo_per_active_player_usd"] = out["theo_usd"] / out["active_players"]
    return out


def protective(pt: pd.DataFrame) -> pd.DataFrame:
    g = pt[pt["gamed"]].copy()
    g["hours_per_visit"] = safe_ratio(g["carded_play_hours"], g["observed_visits"])
    losses = (-g["tracked_net_usd"]).clip(lower=0)
    rows = []
    for name, mask in [("Highest-loss 1%", losses >= losses.quantile(0.99)),
                       ("Longest play per visit 1%", g["hours_per_visit"] >= g["hours_per_visit"].quantile(0.99))]:
        s = g[mask]
        rows.append({"group": name, "players": len(s), "share_of_tracked_losses": losses[mask].sum() / losses.sum(),
                     "share_of_visits": s["observed_visits"].sum() / g["observed_visits"].sum(),
                     "share_of_hours": s["carded_play_hours"].sum() / g["carded_play_hours"].sum(),
                     "median_net_usd": s["tracked_net_usd"].median(), "median_hours_per_visit": s["hours_per_visit"].median(),
                     "median_visits": s["observed_visits"].median()})
    return pd.DataFrame(rows)


PROTECTIVE_SUGGESTIONS = [
    "Session-time reminders on the machine display after 2 hours of continuous carded play (opt-out, not opt-in).",
    "Opt-in loss and time limits through the loyalty app, with a cool-off period before a limit can be raised.",
    "Exclude players who set limits or self-exclude from all promotional mailings and comp offers.",
]


def main() -> None:
    args = window_args("Workstream D: tracked players")
    months = months_in(args.start, args.end)
    pt = player_totals(months)
    write_output("player_totals", pt)
    base = load_base(args.start, args.end)
    ov, hist = overview(pt, base)
    write_output("d2_overview", ov)
    write_output("d2_net_hist", hist)
    conc, lorenz = concentration(pt)
    write_output("d3_concentration", conc)
    write_output("d3_lorenz", lorenz)
    dec = luck_by_decile(pt)
    write_output("d4_luck_players", dec)
    seg = segments(pt)
    write_output("d5_segments", seg)
    mon = monthly(months)
    write_output("d6_monthly", mon)
    prot = protective(pt)
    write_output("d7_protective", prot.assign(suggestions=" | ".join(PROTECTIVE_SUGGESTIONS)))

    # D1 reconciliation: totals equal the sum of player_period over the same months.
    pp = load("player_period")
    pp = pp[pp["period_month"].isin(months)]
    gap = abs(pt["tracked_coin_in_usd"].sum() - pp["tracked_coin_in_usd"].sum()) + abs(pt["theo_usd"].sum() - pp["theo_usd"].sum())
    print(f"D1 {len(pt):,} tracked players; reconciliation gap ${gap:.6f} ({'PASS' if gap < 0.01 else 'FAIL'})")
    o = ov.iloc[0]
    print(f"D2 tracked coin-in ${o.tracked_coin_in_usd / 1e6:,.1f}M ({o.tracked_share_of_all_coin_in:.1%} of all coin-in), "
          f"net ${o.tracked_net_usd / 1e6:,.2f}M, theo ${o.tracked_theo_usd / 1e6:,.2f}M; {o.share_players_ahead:.1%} of "
          f"{o.players_with_carded_play:,} carded players ahead; median net ${o.median_net_usd:,.0f}, mean ${o.mean_net_usd:,.0f}")
    print("D3 " + "; ".join(f"{r.measure} top {r.top_share_of_players:.0%} = {r.share_of_total:.0%}"
                            for r in conc.itertuples() if r.top_share_of_players in (0.01, 0.10))
          + "; gini " + ", ".join(f"{m} {gi:.2f}" for m, gi in conc.groupby("measure")["gini"].first().items()))
    print("D4 share ahead by decile: " + ", ".join(f"{r.decile}:{r.share_ahead:.0%}" for r in dec.itertuples()))
    print("D5 hold by age band: " + ", ".join(f"{r.segment} {r.hold:.1%}" for r in seg[seg.dimension == 'age_band'].itertuples()))
    print("D6\n" + mon.to_string(index=False, float_format=lambda v: f"{v:,.1f}"))
    print("D7\n" + prot.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))


if __name__ == "__main__":
    main()
