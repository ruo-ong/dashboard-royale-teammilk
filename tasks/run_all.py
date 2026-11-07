"""Rebuild every output, in dependency order:  python -m tasks.run_all

Takes about a minute. The dashboard calls this automatically on first start if outputs/ is empty
(e.g. on Streamlit Community Cloud, where outputs/ is not in git).
"""
from __future__ import annotations

import importlib
import sys
import time

ORDER = [
    "f4_machine_day_base",   # F4: the base table every machine task reads
    "a1_manager_list", "a2_exposure", "a3_luck", "a4_leak", "a5_location", "a6_moves", "a8_decomposition", "a11_profit",
    "b_demand", "c_downtime", "b9_story",   # B and C, then the story (needs C2)
    "a9_verdicts",                           # needs B4 (closure) and C7 (chronic)
    "d_players", "e_comps",
    "m_model",                               # needs B2 (event uplift) for the July decision
    "m6_machine_model",                      # machine estimator; uses the July floor forecast (M5)
    "r_plan",                                # needs everything above
    "s1_appendix",                           # docs/APPENDIX.md from the claims log
]


def run(quiet: bool = True) -> None:
    for name in ORDER:
        started = time.perf_counter()
        module = importlib.import_module(f"tasks.{name}")
        argv, sys.argv = sys.argv, [name]  # default analysis window for every task
        try:
            if quiet:
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    module.main()
            else:
                module.main()
        finally:
            sys.argv = argv
        print(f"  {name:<22} {time.perf_counter() - started:5.1f} s", flush=True)


if __name__ == "__main__":
    t = time.perf_counter()
    run(quiet="-v" not in sys.argv)
    print(f"All outputs rebuilt in {time.perf_counter() - t:.0f} s")
