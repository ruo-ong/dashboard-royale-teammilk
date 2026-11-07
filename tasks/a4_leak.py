"""A4 - leak test (payout check): does a machine pay out differently from its configured game math?

Run:  python -m tasks.a4_leak [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a4_leak.parquet              one row per machine: tests, flags, one-line reason
  -> outputs/a4_ticket_changes.parquet    one row per repair / maintenance / move ticket: before vs after
  -> outputs/charts/a4_cumulative_residual.*   running house win - theo for every inspection lead

Wording rule: an unusual pattern is a reason to INSPECT, never proof of wrongdoing.

Tests per machine
  hit-rate z   payout-positive spins vs paid spins x configured hit probability. Very sensitive (huge spin
               counts), so a config mismatch shows up clearly while luck alone stays within +-3.
  hold gap     observed hold - expected hold, read together with luck z (from A3).
  persistence  unlucky in at least 5/6 of its months on the floor AND still unusual (z <= -2) after
               removing its single biggest day, so one jackpot cannot explain it.
  ticket shift for every fault repair / maintenance / move: the 28 days before vs the 28 days after
               (ticket day excluded). Two z-scores: change in hit rate, change in hold gap.
Starting lead rule (tune at Gate 1):
  |hit-rate z| >= 3,  or  luck z <= -3 with persistence,  or  a ticket shift with |z| >= 4.
  The ticket threshold is stricter because ~1,200 tickets x 2 tests would give ~6 false alarms at |z| >= 3.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from royale.charts import COLORS, save, style
from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.timeutil import to_gaming_date
from royale.util import safe_ratio
from tasks import a3_luck
from tasks.a1_manager_list import manager_ten

HIT_Z = 3.0
LUCK_Z = -3.0
PERSIST_SHARE = 5 / 6
PERSIST_EX_BIGGEST_Z = -2.0
MIN_MONTHS = 3
TICKET_WINDOW_DAYS = 28
MIN_SIDE_DAYS = 7
TICKET_SHIFT_Z = 4.0
TICKET_TYPES = ("fault_repair", "scheduled_maintenance", "move")


def ticket_changes(base: pd.DataFrame) -> pd.DataFrame:
    """Hit rate and hold gap in the 28 days before vs after each ticket (ticket day excluded)."""
    ops = load("operations", columns=["operation_id", "machine_id", "event_type", "opened_at_utc"])
    ops = ops[ops["event_type"].isin(TICKET_TYPES)].copy()
    ops["ticket_date"] = to_gaming_date(ops["opened_at_utc"])
    ops = ops[ops["ticket_date"].between(base["gaming_date"].min(), base["gaming_date"].max())]

    cols = ["paid_spins", "payout_positive_spins", "coin_in_usd", "luck_residual_usd", "luck_var_usd2"]
    days = base[["machine_id", "gaming_date", *cols]]
    j = ops[["operation_id", "machine_id", "event_type", "ticket_date"]].merge(days, on="machine_id")
    j["offset"] = (j["gaming_date"] - j["ticket_date"]).dt.days
    j = j[(j["offset"] != 0) & (j["offset"].abs() <= TICKET_WINDOW_DAYS)].copy()
    j["side"] = np.where(j["offset"] < 0, "before", "after")
    j["n_days"] = 1
    wide = j.groupby(["operation_id", "side"])[[*cols, "n_days"]].sum().unstack("side")
    wide.columns = [f"{col}_{side}" for col, side in wide.columns]
    out = ops.set_index("operation_id")[["machine_id", "event_type", "ticket_date"]].join(wide, how="inner")
    out = out.fillna({c: 0 for c in out.columns if c.startswith(("n_days", "paid_spins", "payout_positive", "coin_in"))})

    p_b = safe_ratio(out["payout_positive_spins_before"], out["paid_spins_before"])
    p_a = safe_ratio(out["payout_positive_spins_after"], out["paid_spins_after"])
    pooled = safe_ratio(out["payout_positive_spins_before"] + out["payout_positive_spins_after"],
                        out["paid_spins_before"] + out["paid_spins_after"])
    se_hit = np.sqrt(pooled * (1 - pooled) * (1 / out["paid_spins_before"].where(lambda s: s > 0)
                                              + 1 / out["paid_spins_after"].where(lambda s: s > 0)))
    out["hit_rate_before"], out["hit_rate_after"] = p_b, p_a
    out["hit_change_z"] = safe_ratio(p_a - p_b, se_hit)

    g_b = safe_ratio(out["luck_residual_usd_before"], out["coin_in_usd_before"])  # hold gap = residual / coin-in
    g_a = safe_ratio(out["luck_residual_usd_after"], out["coin_in_usd_after"])
    se_hold = np.sqrt(safe_ratio(out["luck_var_usd2_before"], out["coin_in_usd_before"] ** 2)
                      + safe_ratio(out["luck_var_usd2_after"], out["coin_in_usd_after"] ** 2))
    out["hold_gap_before"], out["hold_gap_after"] = g_b, g_a
    out["hold_change_z"] = safe_ratio(g_a - g_b, se_hold)

    enough = (out["n_days_before"] >= MIN_SIDE_DAYS) & (out["n_days_after"] >= MIN_SIDE_DAYS)
    out.loc[~enough, ["hit_change_z", "hold_change_z"]] = np.nan
    out["shift"] = (out["hit_change_z"].abs() >= TICKET_SHIFT_Z) | (out["hold_change_z"].abs() >= TICKET_SHIFT_Z)
    keep = ["machine_id", "event_type", "ticket_date", "n_days_before", "n_days_after", "hit_rate_before",
            "hit_rate_after", "hit_change_z", "hold_gap_before", "hold_gap_after", "hold_change_z", "shift"]
    return out[keep].reset_index().sort_values(["machine_id", "ticket_date"]).reset_index(drop=True)


def tampering_reports(base: pd.DataFrame) -> pd.Series:
    """Count of reported tampering attempts per machine in the window. Context only, never evidence."""
    inc = load("security_incidents", columns=["machine_id", "category", "occurred_at_utc"])
    inc = inc[inc["machine_id"].notna() & (inc["category"] == "machine_tampering_attempt")].copy()
    inc["gaming_date"] = to_gaming_date(inc["occurred_at_utc"])
    inc = inc[inc["gaming_date"].between(base["gaming_date"].min(), base["gaming_date"].max())]
    return inc.groupby("machine_id").size()


def compute(base: pd.DataFrame, manager_ids: list[str] | None = None):
    """Return (a4_leak per machine, a4_ticket_changes per ticket) for an already-windowed base."""
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    luck, _ = a3_luck.compute(base, manager_ids)
    m = summarize(base, "machine_id")[["machine_id", "days_on_floor", "coin_in_usd", "paid_spins",
                                       "payout_positive_spins", "expected_hits", "hit_rate_z",
                                       "observed_hold", "expected_hold", "luck_residual_usd", "luck_z"]]
    m["hit_ratio"] = safe_ratio(m["payout_positive_spins"], m["expected_hits"])
    m["hold_gap"] = m["observed_hold"] - m["expected_hold"]
    m = m.merge(luck[["machine_id", "months_on_floor", "months_negative", "luck_z_ex_biggest_day"]], on="machine_id")

    monthly = summarize(base, ["machine_id", "month"])
    extreme = monthly.assign(x=monthly["hit_rate_z"].abs() >= HIT_Z).groupby("machine_id")["x"].sum()
    m["months_hit_extreme"] = m["machine_id"].map(extreme).fillna(0).astype(int)

    tickets = ticket_changes(base)
    by_machine = tickets.assign(absz=tickets[["hit_change_z", "hold_change_z"]].abs().max(axis=1))
    strongest = by_machine.sort_values("absz", ascending=False).drop_duplicates("machine_id").set_index("machine_id")
    m["tickets_checked"] = m["machine_id"].map(tickets.groupby("machine_id").size()).fillna(0).astype(int)
    m["ticket_shifts"] = m["machine_id"].map(tickets.groupby("machine_id")["shift"].sum()).fillna(0).astype(int)
    for col in ["event_type", "ticket_date", "hit_change_z", "hold_change_z"]:
        m[f"strongest_ticket_{col}"] = m["machine_id"].map(strongest[col])
    m["tampering_reports"] = m["machine_id"].map(tampering_reports(base)).fillna(0).astype(int)

    m["hit_flag"] = m["hit_rate_z"].abs() >= HIT_Z
    m["persistent"] = ((m["months_on_floor"] >= MIN_MONTHS)
                       & (m["months_negative"] >= np.ceil(PERSIST_SHARE * m["months_on_floor"]))
                       & (m["luck_z_ex_biggest_day"] <= PERSIST_EX_BIGGEST_Z))
    m["luck_flag"] = (m["luck_z"] <= LUCK_Z) & m["persistent"]
    m["ticket_flag"] = m["ticket_shifts"] > 0
    m["inspection_lead"] = m["hit_flag"] | m["luck_flag"] | m["ticket_flag"]
    m["reason"] = m.apply(_reason, axis=1)
    m["in_manager_10"] = m["machine_id"].isin(manager_ids)
    return m.sort_values(["inspection_lead", "hit_rate_z"], ascending=[False, False]).reset_index(drop=True), tickets


def _reason(row) -> str:
    if not row["inspection_lead"]:
        return ""
    parts = []
    if row["hit_flag"]:
        more = "more" if row["hit_ratio"] > 1 else "fewer"
        parts.append(f"pays out on {abs(row['hit_ratio'] - 1):.1%} {more} spins than its configured hit "
                     f"probability (hit-rate z {row['hit_rate_z']:+.0f}; extreme in {row['months_hit_extreme']} of "
                     f"{row['months_on_floor']} months)")
    parts.append(f"hold {row['observed_hold']:.1%} vs {row['expected_hold']:.1%} expected (luck z {row['luck_z']:+.1f})")
    if row["persistent"]:
        parts.append(f"below expectation in {row['months_negative']} of {row['months_on_floor']} months, "
                     f"still z {row['luck_z_ex_biggest_day']:+.1f} without its biggest day")
    if row["ticket_flag"]:
        parts.append(f"behaviour changed after a {row['strongest_ticket_event_type'].replace('_', ' ')} on "
                     f"{pd.Timestamp(row['strongest_ticket_ticket_date']):%b %-d} "
                     f"(hit z {row['strongest_ticket_hit_change_z']:+.1f}, hold z {row['strongest_ticket_hold_change_z']:+.1f})")
    elif row["tickets_checked"]:
        parts.append(f"no repair/maintenance/move ticket explains it ({row['tickets_checked']} checked)")
    if row["tampering_reports"]:
        parts.append(f"{row['tampering_reports']} tampering-attempt report(s), context only")
    return "Inspect: " + "; ".join(parts) + "."


def cumulative_figure(base: pd.DataFrame, leak: pd.DataFrame, tickets: pd.DataFrame) -> go.Figure | None:
    """Running house win - theo for each lead, against the +-2 SD band that luck alone would produce."""
    leads = leak[leak["inspection_lead"]]["machine_id"].tolist()
    if not leads:
        return None
    info = leak.set_index("machine_id")
    titles = [f"<b>{mid}</b> · hit rate {info.loc[mid, 'hit_ratio'] - 1:+.1%} vs its configuration · "
              f"hold {info.loc[mid, 'observed_hold']:.1%} vs {info.loc[mid, 'expected_hold']:.1%} expected" for mid in leads]
    fig = make_subplots(rows=len(leads), cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=titles)
    for i, mid in enumerate(leads, start=1):
        d = base[base["machine_id"] == mid].sort_values("gaming_date")
        cum = d["luck_residual_usd"].cumsum()
        band = 2 * np.sqrt(d["luck_var_usd2"].cumsum())
        x = d["gaming_date"]
        fig.add_trace(go.Scatter(x=pd.concat([x, x[::-1]]), y=pd.concat([band, -band[::-1]]), fill="toself",
                                 fillcolor=COLORS["grid"], line={"width": 0}, hoverinfo="skip",
                                 name="Ordinary luck (±2 SD)", showlegend=i == 1), row=i, col=1)
        fig.add_trace(go.Scatter(x=x, y=cum, mode="lines", line={"color": COLORS["series_1"], "width": 2},
                                 name="House win − theo, running total", showlegend=i == 1,
                                 hovertemplate="%{x|%b %d}: $%{y:,.0f}<extra>" + mid + "</extra>"), row=i, col=1)
        for _, t in tickets[tickets["machine_id"] == mid].iterrows():
            fig.add_vline(x=t["ticket_date"], line={"color": COLORS["text_secondary"], "width": 1, "dash": "dot"},
                          row=i, col=1)
            fig.add_annotation(x=t["ticket_date"], y=1, yref=f"y{'' if i == 1 else i} domain", xanchor="left",
                               text=t["event_type"].replace("_", " "), showarrow=False,
                               font={"size": 11, "color": COLORS["text_secondary"]}, row=i, col=1)
        fig.update_yaxes(tickformat="$,.0f", row=i, col=1)
    style(fig, f"{len(leads)} inspection lead{'s' if len(leads) > 1 else ''}: the house result drifts below what the "
               f"game math allows, outside the band luck explains",
          "Running total of house win − theo by gaming day. Grey band: ±2 standard deviations of luck for the play "
          "recorded so far. Dotted lines: repair, maintenance or move tickets.", height=300 + 260 * len(leads))
    fig.update_layout(legend={"y": -0.08, "yanchor": "top", "x": 0, "xanchor": "left"})
    for title in titles:  # panel titles: left-aligned, text ink
        fig.update_annotations(selector={"text": title}, x=0, xanchor="left", font={"size": 13, "color": COLORS["text"]})
    return fig


def main() -> None:
    args = window_args("A4 leak test")
    base = load_base(args.start, args.end)
    leak, tickets = compute(base)
    write_output("a4_leak", leak)
    write_output("a4_ticket_changes", tickets)
    fig = cumulative_figure(base, leak, tickets)
    if fig is not None:
        save(fig, "a4_cumulative_residual")

    leads = leak[leak["inspection_lead"]]
    print(f"\n{len(leads)} inspection lead(s):")
    for _, row in leads.iterrows():
        tag = " (manager's 10)" if row["in_manager_10"] else ""
        print(f"  {row['machine_id']}{tag}: {row['reason']}")
    hz = leak["hit_rate_z"]
    print(f"\nHit-rate z over {len(leak)} machines: {(hz.abs() >= HIT_Z).sum()} beyond ±{HIT_Z:g}; "
          f"without the leads, sd {hz[~leak['hit_flag']].std():.2f} (≈1 if the game math is honest)")
    tz = tickets[["hit_change_z", "hold_change_z"]]
    print(f"Ticket check: {len(tickets)} tickets, {int(tickets['shift'].sum())} shifts at |z| >= {TICKET_SHIFT_Z:g}; "
          f"sd of change z: hit {tz['hit_change_z'].std():.2f}, hold {tz['hold_change_z'].std():.2f}")
    print(f"Persistent unlucky machines (any luck z): {int(leak['persistent'].sum())}; "
          f"tampering reports on machines in window: {int(leak['tampering_reports'].sum())}")
    print("Wrote outputs/a4_leak.parquet, a4_ticket_changes.parquet" + (", charts/a4_cumulative_residual" if fig else ""))


if __name__ == "__main__":
    main()
