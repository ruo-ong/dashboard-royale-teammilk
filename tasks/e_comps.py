"""Workstream E (Q5) - what did the comp program cost, and did anything about it change?

Run:  python -m tasks.e_comps [--start 2025-01-01 --end 2025-06-30]
  E1 e1_comp_series        daily comp cost / face value / redemptions; ledger vs property_day reconciliation
  E2 comp_weekly, e2_tier_month   reinvestment rate (comp cost / tracked theo) by week, and by tier x month
  E3 e3_weekly, e3_breaks, e3_change, e3_by_tier
                           weekly program metrics, the strongest break in each, the change itself, by tier
  E4 e4_change_impact      before vs after the change: did it pay for itself? (city trend allowed for)
  E5 e5_tier_economics     tracked contribution, comp cost and reinvestment per player by tier
Comp cost is already inside POS cost of goods: never subtract it twice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import con, load, load_base
from royale.outputs import write_output
from royale.paths import table_path
from royale.timeutil import to_gaming_date
from tasks.d_players import months_in, player_totals

EDGE_WEEKS = 3          # E3: a break must have at least this many full weeks on each side
IMPACT_WEEKS = 8        # E4: compare this many full weeks before vs after the change


def _week(s: pd.Series) -> pd.Series:
    return s - pd.to_timedelta(s.dt.day_of_week, unit="D")


def ledger(start, end) -> pd.DataFrame:
    led = load("loyalty_ledger")
    led["gaming_date"] = to_gaming_date(led["event_at_utc"])
    led = led[led["gaming_date"].between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    led["week"] = _week(led["gaming_date"])
    led["available_lag_h"] = (led["available_at_utc"] - led["event_at_utc"]).dt.total_seconds() / 3600
    return led


def comp_series(pdy: pd.DataFrame, led: pd.DataFrame) -> pd.DataFrame:
    red = led[led["event_type"] == "redeem"].groupby("gaming_date").agg(
        redemptions=("loyalty_event_id", "size"), ledger_cost_usd=("economic_cost_cents", lambda c: c.sum() / 100),
        ledger_face_usd=("face_value_cents", lambda c: c.sum() / 100)).reset_index()
    d = pdy[["gaming_date", "comp_cost_usd", "comp_face_value_usd", "pos_cogs_usd", "pos_cash_usd"]].merge(red, on="gaming_date", how="left")
    d["reconcile_gap_usd"] = d["ledger_cost_usd"] - d["comp_cost_usd"]
    return d


def weekly_metrics(led: pd.DataFrame, base: pd.DataFrame, start, end) -> pd.DataFrame:
    th = base.assign(week=_week(base["gaming_date"])).groupby("week")["carded_theo_usd"].sum()
    c = con(include_outputs=False)
    active = c.sql(f"""SELECT date_trunc('week', gaming_date) AS week, count(DISTINCT player_id) AS active_players
                       FROM read_parquet('{table_path("sessions")}')
                       WHERE gaming_date BETWEEN DATE '{pd.Timestamp(start).date()}' AND DATE '{pd.Timestamp(end).date()}'
                       GROUP BY 1""").df().set_index("week")["active_players"]
    aw = led[led["event_type"] == "award"].groupby("week")["points_delta"].sum()
    rd = led[led["event_type"] == "redeem"]
    g = rd.groupby("week").agg(redemptions=("loyalty_event_id", "size"), cost_usd=("economic_cost_cents", lambda x: x.sum() / 100),
                               face_usd=("face_value_cents", lambda x: x.sum() / 100),
                               points_redeemed=("points_delta", lambda x: -x.sum()), redeemers=("player_id", "nunique"))
    tier_moves = led.assign(moved=led["tier_after"] != led["tier_before"]).groupby("week")["moved"].sum()
    w = g.join(aw.rename("points_awarded")).join(th.rename("tracked_theo_usd")).join(active).join(tier_moves.rename("tier_changes"))
    days = led.groupby("week")["gaming_date"].nunique()
    w["days"] = days
    w = w.reset_index()
    w["points_awarded_per_theo_usd"] = w["points_awarded"] / w["tracked_theo_usd"]
    w["points_per_redemption"] = w["points_redeemed"] / w["redemptions"]
    w["points_per_comp_dollar"] = w["points_redeemed"] / w["face_usd"]
    w["cost_per_redemption_usd"] = w["cost_usd"] / w["redemptions"]
    w["redemptions_per_active_player"] = w["redemptions"] / w["active_players"]
    w["reinvestment_rate"] = w["cost_usd"] / w["tracked_theo_usd"]
    w["full_week"] = w["days"] == 7
    return w


METRICS = ["points_awarded_per_theo_usd", "points_per_redemption", "points_per_comp_dollar", "cost_per_redemption_usd",
           "redemptions_per_active_player", "reinvestment_rate", "tier_changes"]


def find_breaks(w: pd.DataFrame) -> pd.DataFrame:
    full = w[w["full_week"]].reset_index(drop=True)
    rows = []
    for m in METRICS:
        y = full[m].to_numpy(dtype=float)
        best = None
        for k in range(EDGE_WEEKS, len(y) - EDGE_WEEKS + 1):
            a, b = y[:k], y[k:]
            t = (b.mean() - a.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
            if best is None or abs(t) > abs(best[1]):
                best = (k, t, a.mean(), b.mean())
        k, t, mb, ma = best
        rows.append({"metric": m, "break_week": full.loc[k, "week"], "t_stat": t, "mean_before": mb, "mean_after": ma,
                     "change_pct": ma / mb - 1})
    return pd.DataFrame(rows).sort_values("t_stat", key=abs, ascending=False).reset_index(drop=True)


def exact_change_date(led: pd.DataFrame) -> tuple[pd.Timestamp, float, float]:
    """Day-level split of points per comp dollar that best separates before from after."""
    rd = led[led["event_type"] == "redeem"]
    d = rd.groupby("gaming_date").apply(lambda g: -g["points_delta"].sum() / (g["face_value_cents"].sum() / 100),
                                        include_groups=False)
    best = None
    for k in range(7, len(d) - 7):
        a, b = d.iloc[:k], d.iloc[k:]
        sse = ((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, d.index[k], a.mean(), b.mean())
    return best[1], best[2], best[3]


def by_tier(led: pd.DataFrame, change: pd.Timestamp) -> pd.DataFrame:
    rd = led[led["event_type"] == "redeem"].copy()
    rd["period"] = np.where(rd["gaming_date"] < change, "before", "after")
    g = rd.groupby(["tier_before", "period"]).agg(redemptions=("loyalty_event_id", "size"),
                                                  points=("points_delta", lambda x: -x.sum()),
                                                  face_usd=("face_value_cents", lambda x: x.sum() / 100),
                                                  cost_usd=("economic_cost_cents", lambda x: x.sum() / 100)).reset_index()
    g["points_per_comp_dollar"] = g["points"] / g["face_usd"]
    g["cost_per_redemption_usd"] = g["cost_usd"] / g["redemptions"]
    return g.rename(columns={"tier_before": "tier"})


def change_impact(w: pd.DataFrame, change: pd.Timestamp) -> pd.DataFrame:
    full = w[w["full_week"]]
    change_week = change - pd.Timedelta(days=change.day_of_week)
    before = full[(full["week"] < change_week) & (full["week"] >= change_week - pd.Timedelta(weeks=IMPACT_WEEKS))]
    after = full[(full["week"] > change_week) & (full["week"] <= change_week + pd.Timedelta(weeks=IMPACT_WEEKS))]
    city = load("city_visitation_monthly", columns=["month", "mean_visitors_per_calendar_day"]).set_index("month")["mean_visitors_per_calendar_day"].astype(float)
    city_b = city[sorted({d.strftime("%Y-%m") for d in before["week"]})].mean()
    city_a = city[sorted({d.strftime("%Y-%m") for d in after["week"]})].mean()
    city_change = city_a / city_b - 1
    rows = []
    for m in ["redemptions", "cost_usd", "active_players", "tracked_theo_usd", "redemptions_per_active_player",
              "reinvestment_rate", "points_per_comp_dollar"]:
        b, a = before[m], after[m]
        se = np.sqrt(b.var(ddof=1) / len(b) + a.var(ddof=1) / len(a))
        rows.append({"metric": m, "weeks_before": len(b), "weeks_after": len(a), "mean_before": b.mean(), "mean_after": a.mean(),
                     "change": a.mean() - b.mean(), "change_pct": a.mean() / b.mean() - 1, "change_low": a.mean() - b.mean() - 2 * se,
                     "change_high": a.mean() - b.mean() + 2 * se, "city_visitors_change_pct": city_change})
    out = pd.DataFrame(rows)
    theo = out.set_index("metric").loc["tracked_theo_usd"]
    cost = out.set_index("metric").loc["cost_usd"]
    # Theo change net of the city trend, per week: what the casino gained beyond what the city would have brought.
    theo_net = theo["mean_after"] - theo["mean_before"] * (1 + city_change)
    theo_se = (theo["change_high"] - theo["change_low"]) / 4
    extra_cost = cost["change"]
    if theo_net - 2 * theo_se > extra_cost:
        verdict = "paid for itself"
    elif theo_net + 2 * theo_se < extra_cost:
        verdict = "did not pay for itself"
    else:
        verdict = "can't tell yet"
    out["theo_change_net_of_city_per_week_usd"] = theo_net
    out["theo_change_net_of_city_low_usd"] = theo_net - 2 * theo_se
    out["theo_change_net_of_city_high_usd"] = theo_net + 2 * theo_se
    out["extra_comp_cost_per_week_usd"] = extra_cost
    out["verdict"] = verdict
    out["change_date"] = change
    return out


def tier_economics(months: list[str]) -> pd.DataFrame:
    pt = player_totals(months)
    g = pt.groupby("tier_end").agg(players=("player_id", "size"), theo_usd=("theo_usd", "sum"),
                                   comp_cost_usd=("comp_cost_usd", "sum"), contribution_usd=("tracked_contribution_usd", "sum"),
                                   coin_in_usd=("tracked_coin_in_usd", "sum")).reset_index()
    g["theo_per_player_usd"] = g["theo_usd"] / g["players"]
    g["comp_cost_per_player_usd"] = g["comp_cost_usd"] / g["players"]
    g["contribution_per_player_usd"] = g["contribution_usd"] / g["players"]
    g["reinvestment_rate"] = g["comp_cost_usd"] / g["theo_usd"]
    order = {"Base": 0, "Gold": 1, "Platinum": 2}
    return g.sort_values("tier_end", key=lambda s: s.map(order)).rename(columns={"tier_end": "tier"}).reset_index(drop=True)


def main() -> None:
    args = window_args("Workstream E: comps")
    pdy = load("property_day", start=args.start, end=args.end)
    base = load_base(args.start, args.end)
    led = ledger(args.start, args.end)
    series = comp_series(pdy, led)
    write_output("e1_comp_series", series)
    w = weekly_metrics(led, base, args.start, args.end)
    write_output("comp_weekly", w)
    pp = load("player_period")
    tm = pp[pp["period_month"].isin(months_in(args.start, args.end))].groupby(["period_month", "tier_end"])[["comp_cost_usd", "theo_usd"]].sum().reset_index()
    tm["reinvestment_rate"] = tm["comp_cost_usd"] / tm["theo_usd"]
    write_output("e2_tier_month", tm)
    breaks = find_breaks(w)
    write_output("e3_breaks", breaks)
    change, before_v, after_v = exact_change_date(led)
    lag = led.loc[led["event_type"] == "redeem", "available_lag_h"]
    write_output("e3_change", pd.DataFrame([{"change_date": change, "metric": "points_per_comp_dollar",
                                             "before": before_v, "after": after_v, "change_pct": after_v / before_v - 1,
                                             "median_system_lag_h": lag.median(), "max_system_lag_h": lag.max()}]))
    tiers = by_tier(led, change)
    write_output("e3_by_tier", tiers)
    impact = change_impact(w, change)
    write_output("e4_change_impact", impact)
    te = tier_economics(months_in(args.start, args.end))
    write_output("e5_tier_economics", te)

    print(f"E1 ledger cost ${series['ledger_cost_usd'].sum():,.2f} vs property_day comp cost ${series['comp_cost_usd'].sum():,.2f} "
          f"(max daily gap ${series['reconcile_gap_usd'].abs().max():.2f})")
    print(f"E2 reinvestment {w['cost_usd'].sum() / w['tracked_theo_usd'].sum():.2%} of tracked theo over the window")
    print("E3 strongest breaks:\n" + breaks.head(4).to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    print(f"   change date {change:%Y-%m-%d}: points per comp dollar {before_v:.2f} -> {after_v:.2f} "
          f"({after_v / before_v - 1:+.0%}); system lag median {lag.median():.2f} h")
    print("   by tier:\n" + tiers.pivot(index="tier", columns="period", values="points_per_comp_dollar").round(2).to_string())
    print("E4\n" + impact[["metric", "mean_before", "mean_after", "change_pct", "change_low", "change_high"]].to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    i = impact.iloc[0]
    print(f"   city visitors {i['city_visitors_change_pct']:+.1%}; theo net of city ${i['theo_change_net_of_city_per_week_usd']:,.0f}/wk "
          f"(${i['theo_change_net_of_city_low_usd']:,.0f} to ${i['theo_change_net_of_city_high_usd']:,.0f}) vs extra comp cost "
          f"${i['extra_comp_cost_per_week_usd']:,.0f}/wk -> {i['verdict']}")
    print("E5\n" + te.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))


if __name__ == "__main__":
    main()
