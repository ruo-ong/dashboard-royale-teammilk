"""Workstream C (Q3) - how much play was lost to downtime, when, and what was the bottleneck?

Run:  python -m tasks.c_downtime [--start 2025-01-01 --end 2025-06-30]
  C1 tickets_clean              one row per ticket: stages, gaming date, shift, zone, manufacturer, planned flag
  C2 c2_downtime_totals         meter vs ticket downtime reconciliation; down hours by day / zone / manufacturer
  C3 downtime_cost              machine x day lost theo (mid / low / high), planned vs unplanned
     c3_hour_of_week            weekday x hour demand index and lost theo (the heatmap)
     c3_ticket_lost_theo        lost theo per ticket (C4's most expensive outages)
  C5 c5_bottleneck, c5_staffing repair stages by shift / weekday / manufacturer / zone; response vs technicians on shift
  C6 manufacturer_reliability   faults per 1,000 available hours (90% interval), repair time and cost
     c6_maintenance_check       faults 30 days before vs after each scheduled maintenance
  C7 c7_chronic                 machines that break most, and repeat faults within 7 days of a repair
  C8 tech_effect                30-day benefit of one more technician on each shift (low / mid / high)

Stage definitions (data note F-C1): over half of fault tickets are typed in AFTER the technician has already
started (median ~8 minutes of paperwork lag), so "work started - recorded" goes negative. We measure the wait
for a technician from when the machine went down: response = work started - opened. recording_lag is reported
separately and is not on the repair's critical path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from royale.cli import window_args
from royale.data import con, load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.paths import table_path
from royale.timeutil import to_gaming_date, to_shift

PLANNED = {"scheduled_maintenance", "move", "install", "retire"}
REPEAT_DAYS = 7
CHRONIC_REPEATS = 4          # 4+ repeat faults within 7 days of a repair (top ~5% of machines)
Z90 = 1.645
TECH_LEAD_DAYS = 7          # action_catalog A-TECH-SHIFT lead days
HORIZON_DAYS = 30


# ---------------- C1 ----------------
def tickets_clean(base: pd.DataFrame) -> pd.DataFrame:
    ops = load("operations")
    t = ops.copy()
    t["gaming_date"] = to_gaming_date(t["opened_at_utc"])
    t = t[t["gaming_date"].between(base["gaming_date"].min(), base["gaming_date"].max())].copy()
    hours = lambda a, b: (t[b] - t[a]).dt.total_seconds() / 3600
    t["recording_lag_h"] = hours("opened_at_utc", "recorded_at_utc")
    t["response_h"] = hours("opened_at_utc", "work_started_at_utc")
    t["repair_h"] = hours("work_started_at_utc", "available_at_utc")
    t["total_h"] = hours("opened_at_utc", "available_at_utc")
    t["recorded_after_work_started"] = t["recorded_at_utc"] > t["work_started_at_utc"]
    t["missing_timestamp"] = t[["recorded_at_utc", "work_started_at_utc", "available_at_utc"]].isna().any(axis=1)
    t["negative_stage"] = (t[["response_h", "repair_h", "total_h"]] < 0).any(axis=1)
    cal = load("calendar_day", columns=["gaming_date", "gaming_day_end_utc"])
    window_end = cal.loc[cal["gaming_date"] == base["gaming_date"].max(), "gaming_day_end_utc"].iloc[0]
    t["open_at_window_end"] = t["available_at_utc"].isna() | (t["available_at_utc"] > window_end)
    t["spans_gaming_days"] = to_gaming_date(t["available_at_utc"]).to_numpy() != t["gaming_date"].to_numpy()
    t["weekday"] = t["gaming_date"].dt.day_name()
    t["local_hour"] = t["opened_at_local"].dt.hour
    t["shift"] = to_shift(t["opened_at_utc"])
    t["planned"] = t["event_type"].isin(PLANNED)
    t["direct_cost_usd"] = t["direct_cost_cents"] / 100
    where = base[["machine_id", "gaming_date", "zone_id", "zone_name", "bank_id", "manufacturer"]]
    t = t.merge(where, on=["machine_id", "gaming_date"], how="left")
    machines = load("machines", columns=["machine_id", "manufacturer"]).rename(columns={"manufacturer": "_m"})
    t = t.merge(machines, on="machine_id", how="left")
    t["manufacturer"] = t["manufacturer"].fillna(t["_m"])
    return t.drop(columns=["_m", "direct_cost_cents"]).sort_values("opened_at_utc").reset_index(drop=True)


# ---------------- C3 building blocks: every down hour, matched to its ticket ----------------
def down_hours(base: pd.DataFrame, tickets: pd.DataFrame) -> pd.DataFrame:
    """One row per (machine-hour with downtime, ticket): seconds of overlap, plus the hour's context."""
    c = con(include_outputs=False)
    c.register("tk", tickets[["operation_id", "machine_id", "event_type", "planned", "opened_at_utc", "available_at_utc"]])
    start, end = base["gaming_date"].min().date(), base["gaming_date"].max().date()
    dh = c.sql(f"""
        WITH dh AS (
            SELECT machine_id, hour_start_utc, gaming_date, local_hour, 3600 - available_seconds AS down_s
            FROM read_parquet('{table_path("machine_hour")}')
            WHERE active AND available_seconds < 3600 AND gaming_date BETWEEN DATE '{start}' AND DATE '{end}')
        SELECT dh.*, tk.operation_id, tk.event_type, tk.planned,
               GREATEST(0, epoch(LEAST(tk.available_at_utc, dh.hour_start_utc + INTERVAL 1 HOUR)
                                 - GREATEST(tk.opened_at_utc, dh.hour_start_utc))) AS overlap_s
        FROM dh LEFT JOIN tk ON tk.machine_id = dh.machine_id
             AND tk.opened_at_utc < dh.hour_start_utc + INTERVAL 1 HOUR AND tk.available_at_utc > dh.hour_start_utc
    """).df()
    # Split each hour's down seconds across overlapping tickets in proportion to overlap.
    dh["overlap_s"] = dh["overlap_s"].fillna(0)
    tot = dh.groupby(["machine_id", "hour_start_utc"])["overlap_s"].transform("sum")
    dh["down_h"] = np.where(tot > 0, dh["down_s"] * dh["overlap_s"] / tot.where(tot > 0, 1), dh["down_s"]) / 3600
    dh["planned"] = dh["planned"].astype("boolean").fillna(False).astype(bool)
    return dh.drop(columns=["overlap_s"])


def hour_of_week_index(base: pd.DataFrame) -> pd.DataFrame:
    """Floor theo per available machine-hour for each gaming weekday x local hour, / overall average."""
    c = con(include_outputs=False)
    rtp = base[["machine_id", "gaming_date", "configured_rtp", "local_weekday"]]
    c.register("rtp", rtp)
    start, end = base["gaming_date"].min().date(), base["gaming_date"].max().date()
    g = c.sql(f"""
        SELECT r.local_weekday, h.local_hour,
               SUM(h.coin_in_cents * (1 - r.configured_rtp)) / 100.0 AS theo_usd,
               SUM(h.available_seconds) / 3600.0 AS available_hours
        FROM read_parquet('{table_path("machine_hour")}') h
        JOIN rtp r ON r.machine_id = h.machine_id AND r.gaming_date = h.gaming_date
        WHERE h.active AND h.gaming_date BETWEEN DATE '{start}' AND DATE '{end}'
        GROUP BY 1, 2
    """).df()
    overall = g["theo_usd"].sum() / g["available_hours"].sum()
    g["tpah"] = g["theo_usd"] / g["available_hours"]
    g["index"] = g["tpah"] / overall
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    g["weekday_order"] = g["local_weekday"].map({d: i for i, d in enumerate(order)})
    return g.sort_values(["weekday_order", "local_hour"]).reset_index(drop=True)


def lost_theo(base: pd.DataFrame, dh: pd.DataFrame, how: pd.DataFrame) -> pd.DataFrame:
    """Expected theo of each down hour = down hours x TPAH x hour-of-week index (machine TPAH mid; bank TPAH bound)."""
    machine_tpah = summarize(base, "machine_id").set_index("machine_id")["tpah"]
    bank_tpah = summarize(base, "bank_id").set_index("bank_id")["tpah"]
    ctx = base[["machine_id", "gaming_date", "local_weekday", "bank_id", "zone_name", "manufacturer", "month"]]
    d = dh.merge(ctx, on=["machine_id", "gaming_date"], how="left")
    d = d.merge(how[["local_weekday", "local_hour", "index"]], on=["local_weekday", "local_hour"], how="left")
    m = d["machine_id"].map(machine_tpah)
    b = d["bank_id"].map(bank_tpah)
    d["lost_theo_usd"] = d["down_h"] * m * d["index"]
    d["lost_theo_low_usd"] = d["down_h"] * np.minimum(m, b) * d["index"]
    d["lost_theo_high_usd"] = d["down_h"] * np.maximum(m, b) * d["index"]
    return d


# ---------------- C5 / C6 / C7 / C8 ----------------
def bottleneck(tickets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = tickets[tickets["event_type"] == "fault_repair"]
    stages = {"recording_lag_h": "Ticket recorded (paperwork)", "response_h": "Wait for technician",
              "repair_h": "Repair", "total_h": "Total out of service"}
    rows = []
    for dim in ["all", "shift", "weekday", "manufacturer", "zone_name"]:
        groups = [("All faults", f)] if dim == "all" else list(f.groupby(dim))
        for key, g in groups:
            for col, label in stages.items():
                rows.append({"dimension": dim, "group": key, "stage": label, "faults": len(g),
                             "mean_h": g[col].mean(), "median_h": g[col].median(), "p90_h": g[col].quantile(0.9)})
    stats = pd.DataFrame(rows)

    roster = load("shift_roster")
    techs = roster[roster["role"] == "slot_tech"].groupby(["gaming_date", "shift"])[["planned_headcount", "actual_headcount"]].sum().reset_index()
    s = f.merge(techs, on=["gaming_date", "shift"], how="left")
    s["short_staffed"] = s["actual_headcount"] < s["planned_headcount"]
    staffing = s.groupby(["shift", "actual_headcount", "short_staffed"]).agg(
        faults=("operation_id", "size"), mean_response_h=("response_h", "mean"), median_response_h=("response_h", "median"),
        share_immediate=("response_h", lambda r: (r <= 0.01).mean()), sd_response_h=("response_h", "std")).reset_index()
    return stats, staffing, s


def reliability(base: pd.DataFrame, tickets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = tickets[tickets["event_type"] == "fault_repair"]
    hours = base.groupby("manufacturer")["available_hours"].sum()
    machines = base.groupby("manufacturer")["machine_id"].nunique()
    g = f.groupby("manufacturer").agg(faults=("operation_id", "size"), mean_total_h=("total_h", "mean"),
                                      repair_cost_usd=("direct_cost_usd", "sum"))
    g = g.join(hours.rename("available_hours")).join(machines.rename("machines")).reset_index()
    n = g["faults"].astype(float)
    lo = n * (1 - 1 / (9 * n) - Z90 / (3 * np.sqrt(n))) ** 3                      # Byar's approximation
    hi = (n + 1) * (1 - 1 / (9 * (n + 1)) + Z90 / (3 * np.sqrt(n + 1))) ** 3        # to the Poisson interval
    per = 1000 / g["available_hours"]
    g["faults_per_1000h"], g["faults_per_1000h_low"], g["faults_per_1000h_high"] = n * per, lo * per, hi * per
    g["repair_cost_per_1000h_usd"] = g["repair_cost_usd"] * per
    g = g.sort_values("faults_per_1000h", ascending=False).reset_index(drop=True)

    pm = tickets[tickets["event_type"] == "scheduled_maintenance"]
    rows = []
    for t in pm.itertuples():
        mine = f[f["machine_id"] == t.machine_id]
        before = ((mine["gaming_date"] < t.gaming_date) & (mine["gaming_date"] >= t.gaming_date - pd.Timedelta(days=30))).sum()
        after = ((mine["gaming_date"] > t.gaming_date) & (mine["gaming_date"] <= t.gaming_date + pd.Timedelta(days=30))).sum()
        rows.append({"operation_id": t.operation_id, "machine_id": t.machine_id, "manufacturer": t.manufacturer,
                     "maintenance_date": t.gaming_date, "faults_30d_before": int(before), "faults_30d_after": int(after)})
    return g, pd.DataFrame(rows)


def chronic(base: pd.DataFrame, tickets: pd.DataFrame, per_ticket: pd.DataFrame) -> pd.DataFrame:
    f = tickets[tickets["event_type"] == "fault_repair"].sort_values(["machine_id", "opened_at_utc"]).copy()
    f["prev_available"] = f.groupby("machine_id")["available_at_utc"].shift()
    f["repeat_within_7d"] = (f["opened_at_utc"] - f["prev_available"]) <= pd.Timedelta(days=REPEAT_DAYS)
    m = summarize(base, "machine_id")[["machine_id", "available_hours", "down_hours", "availability"]]
    agg = f.groupby("machine_id").agg(faults=("operation_id", "size"), repeat_faults=("repeat_within_7d", "sum"),
                                      fault_hours=("total_h", "sum"))
    lt = per_ticket[~per_ticket["planned"]].groupby("machine_id")["lost_theo_usd"].sum().rename("unplanned_lost_theo_usd")
    m = m.join(agg, on="machine_id").join(lt, on="machine_id").fillna({"faults": 0, "repeat_faults": 0, "fault_hours": 0,
                                                                       "unplanned_lost_theo_usd": 0})
    m["faults_per_1000h"] = 1000 * m["faults"] / m["available_hours"]
    cut = m["faults_per_1000h"].quantile(0.95)
    m["chronic"] = (m["faults_per_1000h"] >= cut) | (m["repeat_faults"] >= CHRONIC_REPEATS)
    attrs = base.sort_values("gaming_date").groupby("machine_id")[["zone_name", "manufacturer", "theme"]].last()
    m = m.join(attrs, on="machine_id")
    return m.sort_values(["chronic", "faults_per_1000h"], ascending=False).reset_index(drop=True)


def tech_effect(staffed: pd.DataFrame, per_ticket: pd.DataFrame, n_days: int) -> pd.DataFrame:
    """Benefit of +1 technician on a shift, from the observed response gap between 1 and 2 technicians on duty."""
    s = staffed.merge(per_ticket.groupby("operation_id")[["lost_theo_usd", "down_h"]].sum(), on="operation_id", how="left")
    one, two = s[s["actual_headcount"] == 1], s[s["actual_headcount"] >= 2]
    saved = one["response_h"].mean() - two["response_h"].mean()
    se = np.sqrt(one["response_h"].var() / len(one) + two["response_h"].var() / len(two))
    effective_days = max(0, HORIZON_DAYS - TECH_LEAD_DAYS)
    rows = []
    for shift, g in s.groupby("shift"):
        lost_per_down_h = g["lost_theo_usd"].sum() / g["down_h"].sum()
        faults_per_day = len(g) / n_days
        single = (g["actual_headcount"] == 1).mean()  # a second tech only helps when there is currently one
        for label, w in [("low", max(saved - Z90 * se, 0)), ("mid", saved), ("high", saved + Z90 * se)]:
            rows.append({"shift": shift, "estimate": label, "faults_per_day": faults_per_day,
                         "share_with_one_tech": single, "response_saved_h": w, "lost_theo_per_down_hour_usd": lost_per_down_h,
                         "effective_days": effective_days,
                         "benefit_30d_usd": faults_per_day * effective_days * single * w * lost_per_down_h,
                         "mean_response_1_tech_h": one["response_h"].mean(), "mean_response_2plus_techs_h": two["response_h"].mean()})
    return pd.DataFrame(rows)


def main() -> None:
    args = window_args("Workstream C: downtime")
    base = load_base(args.start, args.end)
    tickets = tickets_clean(base)
    write_output("tickets_clean", tickets)

    dh = down_hours(base, tickets)
    how = hour_of_week_index(base)
    lost = lost_theo(base, dh, how)
    meter = base["down_hours"].sum()
    ticket_hours = tickets["total_h"].sum()
    matched = lost.loc[lost["operation_id"].notna(), "down_h"].sum()
    totals = pd.DataFrame([{"meter_down_hours": meter, "hourly_meter_down_hours": dh.groupby(["machine_id", "hour_start_utc"])["down_s"].first().sum() / 3600,
                            "ticket_hours": ticket_hours, "down_hours_matched_to_ticket": matched,
                            "planned_share": lost.loc[lost["planned"], "down_h"].sum() / lost["down_h"].sum()}])
    write_output("c2_downtime_totals", totals)
    by = []
    for dim in ["gaming_date", "month", "zone_name", "manufacturer", "machine_id"]:
        g = lost.groupby([dim, "planned"])["down_h"].sum().unstack(fill_value=0).rename(columns={True: "planned_h", False: "unplanned_h"})
        g["down_h"] = g.sum(axis=1)
        by.append(g.reset_index().rename(columns={dim: "key"}).assign(dimension=dim))
    write_output("c2_down_hours_by", pd.concat(by, ignore_index=True).astype({"key": str}))

    cost = lost.groupby(["machine_id", "gaming_date", "zone_name", "manufacturer", "month", "planned"])[
        ["down_h", "lost_theo_usd", "lost_theo_low_usd", "lost_theo_high_usd"]].sum().reset_index()
    write_output("downtime_cost", cost)
    grid = lost.groupby(["local_weekday", "local_hour"])[["down_h", "lost_theo_usd"]].sum().reset_index()
    how = how.merge(grid, on=["local_weekday", "local_hour"], how="left").fillna({"down_h": 0, "lost_theo_usd": 0})
    write_output("c3_hour_of_week", how)
    per_ticket = lost[lost["operation_id"].notna()].groupby(["operation_id", "machine_id", "event_type", "planned"])[
        ["down_h", "lost_theo_usd", "lost_theo_low_usd", "lost_theo_high_usd"]].sum().reset_index()
    per_ticket = per_ticket.merge(tickets[["operation_id", "gaming_date", "opened_at_local", "shift", "zone_name",
                                           "manufacturer", "response_h", "repair_h"]], on="operation_id", how="left")
    write_output("c3_ticket_lost_theo", per_ticket.sort_values("lost_theo_usd", ascending=False))

    stats, staffing, staffed = bottleneck(tickets)
    write_output("c5_bottleneck", stats)
    write_output("c5_staffing", staffing)
    rel, pm = reliability(base, tickets)
    write_output("manufacturer_reliability", rel)
    write_output("c6_maintenance_check", pm)
    chron = chronic(base, tickets, per_ticket)
    write_output("c7_chronic", chron)
    tech = tech_effect(staffed, per_ticket, base["gaming_date"].nunique())
    write_output("tech_effect", tech)

    data_notes = {"recorded_after_work_started": int(tickets["recorded_after_work_started"].sum()),
                  "negative_stage": int(tickets["negative_stage"].sum()), "missing": int(tickets["missing_timestamp"].sum()),
                  "open_at_end": int(tickets["open_at_window_end"].sum()), "spans_days": int(tickets["spans_gaming_days"].sum())}
    print(f"C1 {len(tickets)} tickets; data notes: {data_notes}")
    print(f"C2 meter down {meter:,.1f} h | tickets {ticket_hours:,.1f} h | matched {matched:,.1f} h | "
          f"planned share {totals['planned_share'].iloc[0]:.1%}")
    tot = cost[["lost_theo_usd", "lost_theo_low_usd", "lost_theo_high_usd"]].sum()
    print(f"C3 lost theo ${tot['lost_theo_usd']:,.0f} (range ${tot['lost_theo_low_usd']:,.0f}-${tot['lost_theo_high_usd']:,.0f}); "
          f"unplanned ${cost.loc[~cost['planned'], 'lost_theo_usd'].sum():,.0f}")
    print("    by month: " + ", ".join(f"{k} ${v:,.0f}" for k, v in cost.groupby("month")["lost_theo_usd"].sum().items()))
    print(f"    hour-of-week index range {how['index'].min():.2f}-{how['index'].max():.2f}")
    a = stats[stats["dimension"] == "all"].set_index("stage")
    print("C5 all faults (median / p90 h): " + "; ".join(f"{s}: {r.median_h:.2f}/{r.p90_h:.2f}" for s, r in a.iterrows()))
    print(staffing.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print("C6\n" + rel[["manufacturer", "machines", "faults", "faults_per_1000h", "faults_per_1000h_low",
                         "faults_per_1000h_high", "mean_total_h"]].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"    maintenance check: {pm[['machine_id', 'manufacturer', 'faults_30d_before', 'faults_30d_after']].to_dict('records')}")
    print(f"C7 {int(chron['chronic'].sum())} chronic machines: {', '.join(chron.loc[chron['chronic'], 'machine_id'])}")
    print("C8\n" + tech[tech["estimate"] == "mid"][["shift", "faults_per_day", "share_with_one_tech", "response_saved_h",
                                                     "lost_theo_per_down_hour_usd", "benefit_30d_usd"]].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))


if __name__ == "__main__":
    main()
