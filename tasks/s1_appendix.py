"""S1 - render docs/claims_log.csv into docs/APPENDIX.md, the Claims & Evidence appendix for Devpost.

Run:  python -m tasks.s1_appendix
For each claim: the table/query -> result -> alternative explanation tested -> limitation.
Regenerate after editing the claims log; edit the AI-use section below by hand in the CSV-free part of this file.
"""
from __future__ import annotations

import pandas as pd

from royale.paths import ROOT

GROUPS = [("F", "Data notes and foundations"), ("A", "Q1 · The machine trial"), ("B", "Q2 · Demand"),
          ("C", "Q3 · Downtime"), ("D", "Q4 · Tracked players"), ("E", "Q5 · Comps"), ("M", "Forecast model"),
          ("R", "Q6 · The $100k plan")]

AI_USE = """## AI-use disclosure

| Who | Tool | Used for |
| --- | --- | --- |
| Team (shared repo) | Claude (Anthropic), via Claude Code | Planning the work, writing and testing the analysis code (`royale/`, `tasks/`, `tests/`) and the dashboard (`dashboard/`), drafting dashboard text and this appendix. Every number comes from the code in this repository and is checked by automated tests (reconciliations, leakage and budget rules). |
| _each teammate: add a row_ | | |
"""


def render() -> str:
    log = pd.read_csv(ROOT / "docs" / "claims_log.csv").fillna("")
    lines = ["# Claims & Evidence appendix", "",
             "Team Milk · Dashboard Royale (The Gilded Ace is fictional; its data is synthetic).",
             f"Generated from `docs/claims_log.csv` by `python -m tasks.s1_appendix`: {len(log)} claims.",
             "Every table named below is built by `python -m tasks.run_all` into `outputs/`.", ""]
    for prefix, title in GROUPS:
        part = log[log["claim_id"].str.startswith(prefix)]
        if part.empty:
            continue
        lines += [f"## {title}", ""]
        for r in part.itertuples():
            lines += [f"### {r.claim_id} · {r.type}", "", r.claim, "",
                      f"- **Table / query:** `{r.table_query}`", f"- **Result:** {r.result}",
                      f"- **Alternative explanation tested:** {r.alternative_tested}", f"- **Limitation:** {r.limitation}",
                      f"- **Status:** {r.status} · **Dashboard:** {r.dashboard_location}", ""]
    lines += [AI_USE]
    return "\n".join(lines)


def main() -> None:
    text = render()
    (ROOT / "docs" / "APPENDIX.md").write_text(text)
    print(f"Wrote docs/APPENDIX.md ({text.count('### ')} claims)")


if __name__ == "__main__":
    main()
