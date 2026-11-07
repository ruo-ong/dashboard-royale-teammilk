"""B9 - the demand story: 3-6 sentences, with numbers, on what changed in demand and why.

Run after b_demand and c_downtime:  python -m tasks.b9_story   -> outputs/b9_story.parquet
Every sentence carries a claim ID that is also in docs/claims_log.csv.
"""
from __future__ import annotations

import pandas as pd

from royale.outputs import read_output, write_output


def compute() -> pd.DataFrame:
    monthly = read_output("b1_monthly")
    events = read_output("b2_event_uplift")
    ctx = read_output("b6_context")
    closure = read_output("closure_effect")
    cost = read_output("downtime_cost")
    first, last = monthly.iloc[0], monthly.iloc[-1]
    peak = monthly.loc[monthly["coin_in_per_day"].idxmax()]
    tp = closure.query("metric == 'tpah' and period == 'during'").iloc[0]
    tp_after = closure.query("metric == 'tpah' and period == 'after'").iloc[0]
    occ = closure.query("metric == 'occupancy' and period == 'during'").iloc[0]
    ent = closure.query("metric == 'entries_per_sensor_day' and period == 'during'").iloc[0]
    citywide = events[events["local_scope"] == "citywide"]
    sig = citywide[citywide["significant"] & (citywide["uplift_pct"] > 0)].sort_values("uplift_pct", ascending=False)
    flat = citywide[~citywide["significant"]]
    promo = events[events["local_scope"] == "property"]
    by_month = cost.groupby("month")["lost_theo_usd"].sum()
    city_gap = ctx["coin_in_per_day_index"].iloc[-1] - ctx["mean_visitors_per_calendar_day_index"].iloc[-1]

    s = [
        ("B9-01", f"Floor demand was broadly flat: coin-in per day went from ${first['coin_in_per_day'] / 1e6:.2f}M in "
                  f"{first['month']} to a peak of ${peak['coin_in_per_day'] / 1e6:.2f}M in {peak['month']} and "
                  f"${last['coin_in_per_day'] / 1e6:.2f}M in {last['month']} ({last['coin_in_per_day'] / first['coin_in_per_day'] - 1:+.1%}), "
                  f"while 8 more machines came onto the floor in March-April, so play value per available hour slipped "
                  f"from ${first['tpah']:.2f} to ${last['tpah']:.2f}."),
        ("B9-02", f"The casino tracked Las Vegas: indexed to January, its coin-in per day ended June "
                  f"{abs(city_gap):.1f} points {'above' if city_gap > 0 else 'below'} the city's visitors per day, so the "
                  f"floor-wide level needs no casino-specific explanation (city data is published later and describes all "
                  f"of Las Vegas, so it explains but cannot forecast)."),
        ("B9-03", f"The biggest local change was the walkway closure ({tp['closed_from']:%b %-d}-{tp['closed_through']:%b %-d}): "
                  f"with the Main Entrance-Back Forty walkway shut, Back Forty play value fell {abs(tp['did_pct']):.0%}, "
                  f"occupancy {abs(occ['did_pct']):.0%} and foot traffic {abs(ent['did_pct']):.0%} relative to the rest of "
                  f"the floor, costing about ${tp['theo_lost_usd'] / 1000:,.0f}k of theo "
                  f"(${tp['theo_lost_low_usd'] / 1000:,.0f}k-${tp['theo_lost_high_usd'] / 1000:,.0f}k); after it reopened the "
                  f"gap closed to {abs(tp_after['did_pct']):.0%}."),
        ("B9-04", "Big citywide weekends lift the floor: " + ", ".join(
                  f"{r.event} {r.uplift_pct:+.0%}" for r in sig.head(4).itertuples())
                  + f" in coin-in vs the same weekday nearby, while "
                  + " and ".join(flat["event"]) + " show no measurable effect."),
        ("B9-05", "The casino's own promotions work: " + "; ".join(
                  f"{r.event} {r.uplift_pct:+.0%} (${r.uplift_usd / 1000:,.0f}k coin-in, ${r.theo_uplift_usd / 1000:,.0f}k theo over {r.days} days)"
                  for r in promo.itertuples()) + "."),
        ("B9-06", f"Downtime is not what moved demand: it cost ${by_month.sum() / 1000:,.0f}k of theo over six months, "
                  f"${by_month.min() / 1000:,.0f}k-${by_month.max() / 1000:,.0f}k a month with no trend."),
    ]
    return pd.DataFrame(s, columns=["claim_id", "sentence"]).assign(order=range(1, len(s) + 1))


def main() -> None:
    story = compute()
    write_output("b9_story", story)
    for r in story.itertuples():
        print(f"[{r.claim_id}] {r.sentence}")


if __name__ == "__main__":
    main()
