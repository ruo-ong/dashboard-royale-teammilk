"""Workstream B (Q2) - what changed in demand across the floor, and why?

Run:  python -m tasks.b_demand [--start 2025-01-01 --end 2025-06-30]
  B1 b1_floor_trend, b1_monthly    daily floor totals (7-day rolling) and month-over-month change
  B2 b2_weekday, b2_event_uplift   weekday profile; each event's uplift vs the same weekday nearby
  B3 zone_day                      zone x day: theo, occupancy, TPAH, active machines, down hours, step flags
  B5 b5_traffic_daily              cleaned door/zone counters per zone x day, with coverage
  B4 closure_effect                the walkway closure: which zones lost access, difference-in-differences
  B6 b6_context, b6_weather        the casino vs Las Vegas (tourism, weather)
  B8 b8_carded_share               weekly carded share by zone, and machines with sudden drops
(B9, the demand story, needs the downtime totals from C2: see tasks/b9_story.py.)
"""
from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.timeutil import to_gaming_date
from royale.util import safe_ratio

BASELINE_DAYS = 28        # B2: compare an event day with the same weekday within +-4 weeks
STEP_Z = 2.0              # B3: a zone-week this many SDs from its Jan-Feb level is a "step"
LOW_COVERAGE = 0.90       # B5: days with less counter coverage than this are left out of comparisons
DROP_RATIO = 0.5          # B8: carded share below half the machine's usual share = sudden drop


def _property(start=None, end=None) -> pd.DataFrame:
    pdy = load("property_day", start=start, end=end)
    cal = load("calendar_day", start=start, end=end, columns=["gaming_date", "scheduled_seconds", "federal_holiday", "month"])
    return pdy.merge(cal, on="gaming_date")


# ---------------- B1 ----------------
def floor_trend(pdy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pdy[["gaming_date", "local_weekday", "month", "active_machines", "coin_in_usd", "theo_usd", "house_win_usd",
             "occupied_machine_hours", "available_machine_hours"]].copy()
    d["coin_in_per_machine"] = d["coin_in_usd"] / d["active_machines"]
    d["tpah"] = safe_ratio(d["theo_usd"], d["available_machine_hours"])
    d["occupancy"] = safe_ratio(d["occupied_machine_hours"], d["available_machine_hours"])
    for col in ["coin_in_usd", "theo_usd", "tpah", "occupancy"]:
        d[f"{col}_7d"] = d[col].rolling(7, min_periods=7).mean()
    monthly = d.groupby("month").agg(days=("gaming_date", "size"), coin_in_usd=("coin_in_usd", "sum"),
                                     theo_usd=("theo_usd", "sum"), available_machine_hours=("available_machine_hours", "sum"),
                                     occupied_machine_hours=("occupied_machine_hours", "sum"),
                                     avg_active_machines=("active_machines", "mean")).reset_index()
    monthly["coin_in_per_day"] = monthly["coin_in_usd"] / monthly["days"]
    monthly["theo_per_day"] = monthly["theo_usd"] / monthly["days"]
    monthly["tpah"] = monthly["theo_usd"] / monthly["available_machine_hours"]
    monthly["occupancy"] = monthly["occupied_machine_hours"] / monthly["available_machine_hours"]
    for col in ["coin_in_per_day", "theo_per_day", "tpah", "occupancy"]:
        monthly[f"{col}_mom"] = monthly[col].pct_change()
    return d, monthly


# ---------------- B2 ----------------
def event_days() -> pd.DataFrame:
    ev = load("events")
    rows = [{"event_id": e.event_id, "event": e.name, "event_type": e.event_type, "local_scope": e.local_scope,
             "announced_date": e.announced_date, "gaming_date": d}
            for e in ev.itertuples() for d in pd.date_range(e.start_date, e.end_date)]
    return pd.DataFrame(rows)


def weekday_and_events(pdy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    evd = event_days()
    special = set(evd["gaming_date"]) | set(pdy.loc[pdy["federal_holiday"].notna(), "gaming_date"])
    normal = pdy[~pdy["gaming_date"].isin(special)]
    weekday = normal.groupby("local_weekday").agg(days=("gaming_date", "size"), coin_in_usd=("coin_in_usd", "mean"),
                                                  theo_usd=("theo_usd", "mean")).reset_index()
    order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]   # source tables use 3-letter weekdays
    weekday["weekday_order"] = weekday["local_weekday"].str[:3].map({d: i for i, d in enumerate(order)})
    weekday["index_vs_average"] = weekday["coin_in_usd"] / weekday["coin_in_usd"].mean()
    weekday = weekday.sort_values("weekday_order").reset_index(drop=True)

    by_date = pdy.set_index("gaming_date")
    rows = []
    for (eid, name, etype, scope, announced), days in evd.groupby(["event_id", "event", "event_type", "local_scope", "announced_date"]):
        days = [d for d in days["gaming_date"] if d in by_date.index]
        if not days:
            continue
        actual = base_sum = var = 0.0
        actual_theo = base_theo = 0.0
        for d in days:
            wd = by_date.loc[d, "local_weekday"]
            near = normal[(normal["local_weekday"] == wd) & ((normal["gaming_date"] - d).abs() <= pd.Timedelta(days=BASELINE_DAYS))]
            actual += by_date.loc[d, "coin_in_usd"]
            actual_theo += by_date.loc[d, "theo_usd"]
            base_sum += near["coin_in_usd"].mean()
            base_theo += near["theo_usd"].mean()
            var += near["coin_in_usd"].var(ddof=1)  # day-to-day spread of a normal same-weekday day
        uplift = actual - base_sum
        half = 2 * np.sqrt(var)
        rows.append({"event_id": eid, "event": name, "event_type": etype, "local_scope": scope,
                     "announced_date": announced, "start": min(days), "end": max(days), "days": len(days),
                     "coin_in_usd": actual, "baseline_coin_in_usd": base_sum, "uplift_usd": uplift,
                     "uplift_pct": uplift / base_sum, "uplift_low_usd": uplift - half, "uplift_high_usd": uplift + half,
                     "theo_uplift_usd": actual_theo - base_theo, "theo_uplift_pct": (actual_theo - base_theo) / base_theo})
    events = pd.DataFrame(rows).sort_values("start").reset_index(drop=True)
    events["significant"] = (events["uplift_low_usd"] > 0) | (events["uplift_high_usd"] < 0)
    return weekday, events


# ---------------- B3 ----------------
def zone_day(base: pd.DataFrame) -> pd.DataFrame:
    z = summarize(base, ["zone_id", "zone_name", "gaming_date"])
    z = z[["zone_id", "zone_name", "gaming_date", "machines", "theo_usd", "coin_in_usd", "available_hours",
           "occupied_hours", "down_hours", "tpah", "occupancy"]].rename(columns={"machines": "active_machines"})
    floor = z.groupby("gaming_date")["theo_usd"].transform("sum")
    z["share_of_floor_theo"] = z["theo_usd"] / floor
    z["week"] = z["gaming_date"] - pd.to_timedelta(z["gaming_date"].dt.day_of_week, unit="D")
    weekly = z.groupby(["zone_id", "week"])[["theo_usd", "available_hours"]].sum()
    weekly["tpah"] = weekly["theo_usd"] / weekly["available_hours"]
    weekly = weekly.reset_index()
    ref = weekly[weekly["week"] < pd.Timestamp("2025-03-01")].groupby("zone_id")["tpah"].agg(["mean", "std"])
    weekly = weekly.join(ref, on="zone_id")
    weekly["week_step_z"] = (weekly["tpah"] - weekly["mean"]) / weekly["std"]
    z = z.merge(weekly[["zone_id", "week", "week_step_z"]], on=["zone_id", "week"], how="left")
    z["week_step_flag"] = z["week_step_z"].abs() >= STEP_Z
    return z.sort_values(["zone_id", "gaming_date"]).reset_index(drop=True)


# ---------------- B5 ----------------
def traffic_daily(zd: pd.DataFrame) -> pd.DataFrame:
    t = load("zone_traffic_hourly", columns=["sensor_id", "zone_id", "hour_start_utc", "entries_count",
                                              "counter_status", "coverage_minutes"])
    t["gaming_date"] = to_gaming_date(t["hour_start_utc"])
    t = t[t["gaming_date"].notna()]
    scale = np.where(t["counter_status"] == "partial", safe_ratio(60, t["coverage_minutes"]), 1.0)
    t["entries_scaled"] = np.where(t["counter_status"] == "offline", np.nan, t["entries_count"] * scale)
    cal = load("calendar_day", columns=["gaming_date", "scheduled_seconds"])
    d = t.groupby(["zone_id", "sensor_id", "gaming_date"]).agg(
        entries_observed=("entries_count", "sum"), entries_scaled=("entries_scaled", "sum"),
        coverage_minutes=("coverage_minutes", "sum"),
        offline_hours=("counter_status", lambda s: int((s == "offline").sum())),
        partial_hours=("counter_status", lambda s: int((s == "partial").sum()))).reset_index()
    d = d.merge(cal, on="gaming_date")
    d["coverage_share"] = d["coverage_minutes"] / (d["scheduled_seconds"] / 60)
    d["low_coverage"] = d["coverage_share"] < LOW_COVERAGE
    # Scale a partly covered day up to a full day (assumption, stated): entries / coverage share.
    d["entries_full_day_est"] = safe_ratio(d["entries_scaled"], d["coverage_share"].clip(upper=1.0))
    d = d.merge(zd[["zone_id", "gaming_date", "theo_usd"]], on=["zone_id", "gaming_date"], how="left")
    d["theo_per_1000_entries"] = safe_ratio(d["theo_usd"] * 1000, d["entries_full_day_est"])
    return d.drop(columns="scheduled_seconds")


# ---------------- B4 ----------------
def _shortest_from_entrances(edges: list[tuple[str, str, float]], entrance_zones: set[str]) -> dict[str, float]:
    graph: dict[str, list[tuple[str, float]]] = {}
    for a, b, w in edges:
        graph.setdefault(a, []).append((b, w))
        graph.setdefault(b, []).append((a, w))
    dist = {z: 0.0 for z in entrance_zones}
    heap = [(0.0, z) for z in entrance_zones]
    while heap:
        d, z = heapq.heappop(heap)
        if d > dist.get(z, np.inf):
            continue
        for nxt, w in graph.get(z, []):
            if d + w < dist.get(nxt, np.inf):
                dist[nxt] = d + w
                heapq.heappush(heap, (d + w, nxt))
    return dist


def closure_effect(zd: pd.DataFrame, traffic: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    walk = load("floor_walkways")
    closed = walk[walk["closed_from_utc"].notna()].iloc[0]
    start = to_gaming_date(closed["closed_from_utc"])
    end = to_gaming_date(closed["closed_to_utc"]) - pd.Timedelta(days=1)  # closed_to is exclusive
    floor = load("floor_locations")
    entrances = set(floor.loc[floor["node_type"] == "entrance", "zone_id"])
    edges = [(w.zone_a, w.zone_b, w.length_m) for w in walk.itertuples()]
    open_edges = [e for e, w in zip(edges, walk.itertuples()) if w.walkway_id != closed["walkway_id"]]
    before_m = _shortest_from_entrances(edges, entrances)
    during_m = _shortest_from_entrances(open_edges, entrances)
    zones = sorted(before_m)
    affected = {z for z in zones if during_m.get(z, np.inf) > before_m[z] + 1e-9}

    z = zd.copy()
    z["group"] = np.where(z["zone_id"].isin(affected), "affected", "unaffected")
    z["period"] = np.select([z["gaming_date"] < start, z["gaming_date"] <= end], ["before", "during"], "after")
    g = z.groupby(["group", "period"])[["theo_usd", "available_hours", "occupied_hours"]].sum()
    g["tpah"] = g["theo_usd"] / g["available_hours"]
    g["occupancy"] = g["occupied_hours"] / g["available_hours"]

    t = traffic[~traffic["low_coverage"]].copy()
    t["group"] = np.where(t["zone_id"].isin(affected), "affected", "unaffected")
    t["period"] = np.select([t["gaming_date"] < start, t["gaming_date"] <= end], ["before", "during"], "after")
    entries = t.groupby(["group", "period"]).agg(entries=("entries_full_day_est", "sum"), sensor_days=("gaming_date", "size"))
    entries["entries_per_sensor_day"] = entries["entries"] / entries["sensor_days"]
    g = g.join(entries[["entries_per_sensor_day"]])

    # Weekly affected/unaffected TPAH ratio -> effect and a range from the before-period's week-to-week spread.
    z["week"] = z["gaming_date"] - pd.to_timedelta(z["gaming_date"].dt.day_of_week, unit="D")
    wk = z.groupby(["week", "group"])[["theo_usd", "available_hours"]].sum().unstack("group")
    ratio = (wk[("theo_usd", "affected")] / wk[("available_hours", "affected")]) / \
            (wk[("theo_usd", "unaffected")] / wk[("available_hours", "unaffected")])
    weeks_before = ratio[ratio.index + pd.Timedelta(days=6) < start]
    weeks_during = ratio[(ratio.index >= start) & (ratio.index + pd.Timedelta(days=6) <= end)]

    rows = []
    for metric in ["tpah", "occupancy", "entries_per_sensor_day"]:
        for period in ["during", "after"]:
            a_b, a_p = g.loc[("affected", "before"), metric], g.loc[("affected", period), metric]
            u_b, u_p = g.loc[("unaffected", "before"), metric], g.loc[("unaffected", period), metric]
            rows.append({"metric": metric, "period": period, "affected_before": a_b, "affected_period": a_p,
                         "unaffected_before": u_b, "unaffected_period": u_p,
                         "did_abs": (a_p - a_b) - (u_p - u_b), "did_pct": (a_p / a_b) / (u_p / u_b) - 1})
    effect = pd.DataFrame(rows)

    # Theo lost during the closure: affected available hours x (counterfactual TPAH - actual TPAH).
    a_hours = g.loc[("affected", "during"), "available_hours"]
    rel = effect.query("metric == 'tpah' and period == 'during'")["did_pct"].iloc[0]
    counterfactual = g.loc[("affected", "during"), "tpah"] / (1 + rel)
    se = weeks_before.std(ddof=1) / weeks_before.mean() / np.sqrt(max(len(weeks_during), 1))
    actual = g.loc[("affected", "during"), "tpah"]
    lost_mid = a_hours * (counterfactual - actual)
    lost_low = a_hours * (actual / (1 + rel + 2 * se) - actual)    # smaller drop -> smaller loss
    lost_high = a_hours * (actual / (1 + rel - 2 * se) - actual)
    summary = {"walkway_id": closed["walkway_id"], "reason": closed["closure_reason"],
               "closed_from": start, "closed_through": end, "days_closed": (end - start).days + 1,
               "affected_zones": sorted(affected),
               "walk_before_m": {k: before_m[k] for k in sorted(affected)},
               "walk_during_m": {k: during_m[k] for k in sorted(affected)},
               "tpah_did_pct_during": rel,
               "tpah_did_pct_after": effect.query("metric == 'tpah' and period == 'after'")["did_pct"].iloc[0],
               "theo_lost_usd": lost_mid, "theo_lost_low_usd": min(lost_low, lost_high),
               "theo_lost_high_usd": max(lost_low, lost_high)}
    for k, v in summary.items():
        effect[k] = [v] * len(effect) if isinstance(v, (list, dict)) else v
    effect["affected_zones"] = ", ".join(sorted(affected))
    effect = effect.drop(columns=["walk_before_m", "walk_during_m"])
    return effect, summary


# ---------------- B6 ----------------
def context(pdy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    city = load("city_visitation_monthly", columns=["month", "visitor_volume", "mean_visitors_per_calendar_day",
                                                    "convention_attendance", "hotel_occupancy_ratio"])
    casino = pdy.groupby("month").agg(coin_in_usd=("coin_in_usd", "sum"), theo_usd=("theo_usd", "sum"),
                                      days=("gaming_date", "size")).reset_index()
    casino["coin_in_per_day"] = casino["coin_in_usd"] / casino["days"]
    m = casino.merge(city, on="month", how="left")
    for col in ["coin_in_per_day", "mean_visitors_per_calendar_day", "convention_attendance", "hotel_occupancy_ratio"]:
        m[f"{col}_index"] = 100 * m[col].astype(float) / float(m[col].iloc[0])
    gap = m["coin_in_per_day_index"].iloc[-1] - m["mean_visitors_per_calendar_day_index"].iloc[-1]
    corr = np.corrcoef(m["coin_in_per_day_index"], m["mean_visitors_per_calendar_day_index"].astype(float))[0, 1]

    w = load("weather_daily", columns=["source_date", "tmax_c", "prcp_mm"]).rename(columns={"source_date": "gaming_date"})
    w["gaming_date"] = pd.to_datetime(w["gaming_date"])
    d = pdy[["gaming_date", "local_weekday", "coin_in_usd"]].merge(w, on="gaming_date", how="left")
    d["coin_in_vs_weekday"] = d["coin_in_usd"] / d.groupby("local_weekday")["coin_in_usd"].transform("mean")
    d["tmax_c"] = d["tmax_c"].astype(float)
    d["prcp_mm"] = d["prcp_mm"].astype(float)
    weather = {"corr_tmax": d[["coin_in_vs_weekday", "tmax_c"]].corr().iloc[0, 1],
               "corr_rain": d[["coin_in_vs_weekday", "prcp_mm"]].corr().iloc[0, 1],
               "rain_days": int((d["prcp_mm"] > 0).sum())}
    info = {"casino_minus_city_points_june": gap, "monthly_corr_casino_city": corr, **weather}
    return m, d, info


# ---------------- B8 ----------------
def carded_share(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = base[["machine_id", "zone_name", "gaming_date", "coin_in_usd", "carded_coin_in_usd"]].copy()
    b["week"] = b["gaming_date"] - pd.to_timedelta(b["gaming_date"].dt.day_of_week, unit="D")
    zone_week = b.groupby(["zone_name", "week"])[["coin_in_usd", "carded_coin_in_usd"]].sum().reset_index()
    floor_week = b.groupby("week")[["coin_in_usd", "carded_coin_in_usd"]].sum().reset_index().assign(zone_name="All floor")
    zone_week = pd.concat([zone_week, floor_week], ignore_index=True)
    zone_week["carded_share"] = zone_week["carded_coin_in_usd"] / zone_week["coin_in_usd"]

    mw = b.groupby(["machine_id", "week"])[["coin_in_usd", "carded_coin_in_usd"]].sum().reset_index()
    mw = mw[mw["coin_in_usd"] > 0]
    mw["share"] = mw["carded_coin_in_usd"] / mw["coin_in_usd"]
    mw["usual"] = mw.groupby("machine_id")["share"].transform("median")
    mw["drop"] = mw["share"] < DROP_RATIO * mw["usual"]
    drops = mw[mw["drop"]].groupby("machine_id").agg(weeks_dropped=("week", "size"), first_week=("week", "min"),
                                                     lowest_share=("share", "min"), usual_share=("usual", "first")).reset_index()
    return zone_week, drops


def main() -> None:
    args = window_args("Workstream B: demand")
    pdy = _property(args.start, args.end)
    base = load_base(args.start, args.end)

    daily, monthly = floor_trend(pdy)
    write_output("b1_floor_trend", daily)
    write_output("b1_monthly", monthly)
    weekday, events = weekday_and_events(pdy)
    write_output("b2_weekday", weekday)
    write_output("b2_event_uplift", events)
    zd = zone_day(base)
    write_output("zone_day", zd)
    traffic = traffic_daily(zd)
    write_output("b5_traffic_daily", traffic)
    effect, closure = closure_effect(zd, traffic)
    write_output("closure_effect", effect)
    ctx, weather, info = context(pdy)
    write_output("b6_context", ctx)
    write_output("b6_weather", weather)
    zone_week, drops = carded_share(base)
    write_output("b8_carded_share", zone_week)
    write_output("b8_carded_drops", drops)

    print("B1 monthly:\n" + monthly[["month", "coin_in_per_day", "coin_in_per_day_mom", "tpah", "occupancy",
                                     "avg_active_machines"]].to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    print("\nB2 events:\n" + events[["event", "local_scope", "days", "uplift_usd", "uplift_pct", "uplift_low_usd",
                                     "uplift_high_usd", "significant"]].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print("\nB2 weekday index: " + ", ".join(f"{r.local_weekday[:3]} {r.index_vs_average:.2f}" for r in weekday.itertuples()))
    print(f"\nB4 closure {closure['walkway_id']} {closure['closed_from']:%b %d}-{closure['closed_through']:%b %d} "
          f"({closure['days_closed']} days): affected {closure['affected_zones']} "
          f"(walk {closure['walk_before_m']} m -> {closure['walk_during_m']} m)")
    print(effect[["metric", "period", "affected_before", "affected_period", "unaffected_before", "unaffected_period",
                  "did_pct"]].to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    print(f"Theo lost to the closure: ${closure['theo_lost_usd']:,.0f} (range ${closure['theo_lost_low_usd']:,.0f}"
          f"-${closure['theo_lost_high_usd']:,.0f})")
    print(f"\nB5 traffic: {int(traffic['low_coverage'].sum())} low-coverage sensor-days of {len(traffic)}")
    print(f"B6: casino minus city (visitors/day index, June, Jan=100): {info['casino_minus_city_points_june']:+.1f} points; "
          f"monthly corr {info['monthly_corr_casino_city']:.2f}; weather corr tmax {info['corr_tmax']:+.2f}, "
          f"rain {info['corr_rain']:+.2f}")
    print(f"B8: floor carded share {zone_week.query('zone_name == \"All floor\"')['carded_share'].mean():.1%}; "
          f"{len(drops)} machines with sudden carded-share drops")
    print("Wrote b1_floor_trend, b1_monthly, b2_weekday, b2_event_uplift, zone_day, b5_traffic_daily, closure_effect, "
          "b6_context, b6_weather, b8_carded_share, b8_carded_drops")


if __name__ == "__main__":
    main()
