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

**Build everything, test it, open the dashboard** (outputs/ is gitignored, so rebuild after every pull):

```sh
python -m tasks.run_all          # every output table in dependency order (~1 min)
pytest -q                        # 91 checks: reconciliations, leakage, budget rules, every dashboard page
streamlit run dashboard/app.py      # version 1: the report (http://localhost:8501)
streamlit run dashboard/app_v2.py   # version 2: the report plus the machine estimator
```

| Workstream | Script(s) | Main outputs |
| --- | --- | --- |
| F · foundations | `tasks/f4_machine_day_base.py` | `machine_day_base` |
| A · Q1 machine trial | `tasks/a1_manager_list.py` … `a11_profit.py`, `a9_verdicts.py` | `a2_exposure`, `a3_luck`, `a4_leak`, `a5_location`, `bank_scores`, `a6_moves`, `a8_decomposition`, `a11_profit`, `machine_verdicts` |
| B · Q2 demand | `tasks/b_demand.py`, `tasks/b9_story.py` | `b1_floor_trend`, `b2_event_uplift`, `zone_day`, `b5_traffic_daily`, `closure_effect`, `b6_context`, `b9_story` |
| C · Q3 downtime | `tasks/c_downtime.py` | `tickets_clean`, `downtime_cost`, `c3_hour_of_week`, `c5_staffing`, `manufacturer_reliability`, `c7_chronic`, `tech_effect` |
| D · Q4 tracked players | `tasks/d_players.py` | `player_totals`, `d3_concentration`, `d4_luck_players`, `d5_segments`, `d7_protective` |
| E · Q5 comps | `tasks/e_comps.py` | `comp_weekly`, `e3_change`, `e4_change_impact`, `e5_tier_economics` |
| M · forecast model | `tasks/m_model.py` ([protocol](docs/MODEL_PROTOCOL.md) committed first; [write-up](docs/MODEL.md)) | `forecast_results`, `m4_metrics`, `m5_decision` |
| M6 · machine estimator | `tasks/m6_machine_model.py` (location + game + manufacturer; time-split validated) | `m6_validation`, `m6_coefficients`, `m6_settings` |
| R · Q6 $100k plan | `tasks/r_plan.py` | `r1_costs`, `r3_benefits`, `portfolio`, `r5_sensitivity`, `r6_measurement`, `r7_tradeoffs` |
| S · submission | `tasks/s1_appendix.py` | [docs/APPENDIX.md](docs/APPENDIX.md) (Claims & Evidence appendix) |
| W · dashboard | `dashboard/app.py` (v1), `dashboard/app_v2.py` (v2, adds the estimator); shared `shell.py`, `ui.py`, `views/*.py` | reads only `outputs/` |

Any task also runs alone (`python -m tasks.a2_exposure --start 2025-04-01 --end 2025-06-30`); each exposes a
`compute(...)` function, which is how the machine-trial page recomputes live for any period.
Charts are also written to `outputs/charts/` as HTML (and PNG when Chrome is installed).

**Deploy (public link for judges):** push to GitHub, then on [share.streamlit.io](https://share.streamlit.io) create an app
from this repo with main file `dashboard/app.py` (or `dashboard/app_v2.py` for version 2) (Python 3.12). `outputs/` is not in git, so the app builds it on first
start (about a minute). Test the link in a private browser window.

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
