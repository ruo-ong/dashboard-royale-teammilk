# Dashboard Royale

## Team Milk: how to run

**One-time setup** (Python 3.11+, from the repo folder):

```sh
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt    # pinned versions + our royale/ helper package
python scripts/verify_data.py      # both must print PASS
python scripts/verify_semantics.py
```

**Build the shared tables** (outputs/ is gitignored, so rebuild after every pull):

```sh
python -m tasks.f4_machine_day_base   # -> outputs/machine_day_base.parquet, reconciliation must print all PASS
python -m tasks.a1_manager_list       # -> a1_manager_list           (the GM's bottom 10, Jan-Jun)
python -m tasks.a2_exposure           # -> a2_exposure               (+ charts/a2_rank_shift)
python -m tasks.a3_luck               # -> a3_luck, a3_luck_monthly  (+ charts/a3_luck_z_hist)
python -m tasks.a5_location           # -> a5_location, bank_scores, a5_game_by_zone (+ charts/a5_floor_map)
python -m tasks.a4_leak               # -> a4_leak, a4_ticket_changes (+ charts/a4_cumulative_residual)
python -m tasks.a6_moves              # -> a6_moves
python -m tasks.a8_decomposition      # -> a8_decomposition          (+ charts/a8_decomposition)
python -m tasks.a11_profit            # -> a11_profit
pytest -q                             # all checks
```

Analysis tasks take `--start YYYY-MM-DD --end YYYY-MM-DD` (default: the full Jan 1 - Jun 30 window).
Each one also exposes a `compute(base, ...)` function, so the dashboard can recompute it live for any date range.
Charts are written to `outputs/charts/` as HTML (and PNG when Chrome is installed).

**Use the helpers** instead of hand-rolling filters, unit conversions or time zones:

```python
from royale.data import load, window, con          # load("machine_day", start=..., end=...): on-floor rows only by default
from royale.timeutil import to_gaming_date, to_shift  # UTC timestamp -> gaming date / shift (DST-safe)
from royale.util import cents_to_usd, safe_ratio
from royale.outputs import read_output, write_output  # outputs/<name>.parquet
from royale.metrics import summarize                  # all shared metrics as ratios of sums

base = window(read_output("machine_day_base"), "2025-01-01", "2025-06-30")
by_machine = summarize(base, "machine_id")   # tpah, availability, luck_z, hit_rate_z, ...
```

**Conventions**

- Each task writes one table with `write_output("<task id>_<name>", df)`, e.g. `a3_luck`. Hand-off tables keep their names from the plan (`machine_verdicts`, `zone_day`, ...). The dashboard reads only `outputs/`.
- Task scripts go in `tasks/` and run with `python -m tasks.<file>` from the repo root.
- Metric definitions: [docs/METRICS.md](docs/METRICS.md). Log every claim as you go: [docs/claims_log.csv](docs/claims_log.csv).
- DuckDB 2.0: query results have no `.fetchone()`. Use `.fetchall()[0]` or `.df()`.

---

## Luck, Location, or a Leak?

> Management is about to replace the ten machines that earned the least. Your dashboard could stop an expensive mistake—or show that management is right.
>
> Investigate six months at a fictional 300-machine casino. Explain what changed in demand, payouts, availability, and contribution. Show what tracked players wagered, received back, and actually won or lost. Recommend up to three actions within a $100,000 operations budget for the next 30 days, with evidence, uncertainty, and a way to measure success. Include one useful basic ML or time-series method. You may recommend an experiment, an inspection, or preserving the budget.

Fictional casino; synthetic data calibrated to public aggregates.

> **Draft release:** the data is `0.9.0-draft`. See the [release readiness review](reference/READINESS.md) for outstanding organizer tasks before sharing publicly.

**New here? Start with the [participant guide](GUIDE.md).** It covers the challenge, setup, the datasets, common mistakes and how to submit.

🎰 **[View the example dashboard](https://tamu-datathon-org.github.io/dashboard-royale/example-dashboard.html)** (layout only; all values are placeholders)

| | |
| --- | --- |
| 📘 [Participant guide](GUIDE.md) | The challenge, setup, datasets, common issues, submission |
| 📂 [`data/`](data/) | All tables, as `.parquet` and `.csv.gz` |
| 📑 [Dataset reference](reference/DATASET.md) | Layout, row counts, conventions, money definitions |
| 📖 [Data dictionary](reference/DATA_DICTIONARY.md) | Every table and column |
| 🔗 [Sources](reference/SOURCES.md) | Where the real-world files come from |

Original documentation, scripts and synthetic data use the [MIT license](LICENSE).
Third-party source tables are excluded; see [publisher terms](reference/SOURCE_TERMS.md).

Before publishing, run `python scripts/verify_data.py` and
`python scripts/check_release.py` (requires Python 3.11+ and DuckDB).
The release check currently reports missing calibration and publisher evidence.
