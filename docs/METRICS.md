# Shared metric definitions

Everyone uses these exact formulas so numbers match across pages. Sums run over **on-floor machine-days in the chosen period** (`outputs/machine_day_base.parquet`).
They are implemented once in [`royale/metrics.py`](../royale/metrics.py) (`summarize()`): use that instead of re-deriving them.

**Changing a definition?** Update this file *and* `royale/metrics.py`, and tell the team.

| Metric | Formula | Column in `summarize()` | Notes |
| --- | --- | --- | --- |
| On-floor hours | Σ `scheduled_seconds` (machine_day) ÷ 3600 | `on_floor_hours` | machine_day's scheduled seconds only count time on the floor |
| Available hours | Σ `available_seconds` ÷ 3600 | `available_hours` | On-floor time minus repairs, moves, installs |
| Down hours | On-floor hours − available hours | `down_hours` | |
| Availability | Σ available ÷ Σ scheduled | `availability` | "Was it working?" |
| Occupancy | Σ occupied ÷ Σ available | `occupancy` | "When it worked, did people sit down?" |
| TPAH | Σ theo ÷ available hours | `tpah` | **Theo per available hour.** The main luck-free, exposure-free demand measure |
| Coin-in per available hour | Σ coin-in ÷ available hours | `coin_in_per_avail_hour` | Play volume, ignoring RTP differences |
| Observed hold | Σ house win ÷ Σ coin-in | `observed_hold` | Null when coin-in is 0 |
| Expected hold | Σ theo ÷ Σ coin-in | `expected_hold` | Equals 1 − RTP, weighted if the config changed |
| Luck residual | Σ house win − Σ theo | `luck_residual_usd` | Negative = the house was unlucky |
| Luck SD | √ Σ (`sum_bet_squared` × `payout_multiplier_variance`) ÷ 100 | `luck_sd_usd` | Dollars. Size of a "normal" luck swing, computed per day with that day's config (`luck_var_usd2` per row, summed, then √) |
| Luck z | Luck residual ÷ luck SD | `luck_z` | Within ±2 is ordinary luck |
| Hit-rate z | (Σ payout-positive spins − Σ paid spins × p) ÷ √(Σ paid spins × p × (1 − p)) | `hit_rate_z` | p = `hit_probability` from game_math. Very sensitive because of the huge spin counts |
| Contribution | `contribution_after_supplied_costs_usd` | `contribution_usd` | House win minus lease, service, power and repair |
| Lost theo (downtime) | Down hours × the machine's TPAH × hour-of-week index | (task C3) | Defined in C3 |
| Reinvestment rate | Comp economic cost ÷ tracked theo | (task E2) | Always state the period |
| Tracked contribution | Tracked win + linked POS cash − linked POS cost | (task E5) | Comp cost is already inside POS cost |
| MAE | Mean of \|forecast − actual\|, in dollars | (task M2–M4) | Model accuracy |

## Ground rules (from the guide's "common issues")

1. Drop off-floor rows (`meter_status != 'reported'`, 1,018 rows). They are not zero sales. `load()` and `machine_day_base` already do this.
2. Ratio of sums, never the average of daily ratios.
3. `_cents` are integer cents, `_usd` are dollars. Convert once, early (`machine_day_base` is all dollars).
4. Never assume 24 hours: 2025-03-08 has 23. Use `scheduled_seconds`.
5. Aggregate each fact table to the shared grain first, then join.
6. Every calculation takes a start and end date. Judges change the analysis period.
7. Time-based train/test splits only; no information from after the prediction date.
8. Player tables are loyalty-card play only: label them **tracked**.
9. Comp cost is already inside POS cost of goods: subtract it once.
10. Unusual means **inspect**, never "fraud" or "cheating".
11. Use theo for demand and benefits; house win contains luck.
12. Log every claim in [`claims_log.csv`](claims_log.csv) as you go.
