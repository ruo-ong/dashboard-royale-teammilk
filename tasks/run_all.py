"""Rebuild every output, in dependency order:  python -m tasks.run_all

Takes about a minute. The dashboard calls run(force=False) on start-up when outputs/ is missing or out of date
(for example on Streamlit Community Cloud, where outputs/ is not in git).

Safe when several sessions start at once: a lock lets only one build run at a time, and a session that waited
finds the finished outputs and returns. A marker file records that a build finished for the current code and
data, so a crashed or partial build is never mistaken for a complete one.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import os
import sys
import threading
import time

from royale.paths import DATA, OUTPUTS, ROOT

ORDER = [
    "f4_machine_day_base",   # F4: the base table every machine task reads
    "a1_manager_list", "a2_exposure", "a3_luck", "a4_leak", "a5_location", "a6_moves", "a8_decomposition", "a11_profit",
    "b_demand", "c_downtime", "b9_story",   # B and C, then the story (needs C2)
    "a9_verdicts",                           # needs B4 (closure) and C7 (chronic)
    "a12_floor_screen",                      # floor-wide screen; uses the verdicts' flags
    "d_players", "e_comps",
    "m_model",                               # needs B2 (event uplift) for the July decision
    "m6_machine_model",                      # machine estimator; uses the July floor forecast (M5)
    "r_plan",                                # needs everything above
    "s1_appendix",                           # docs/APPENDIX.md from the claims log
]
MARKER = OUTPUTS / "_build_complete.json"
_THREAD_LOCK = threading.Lock()


def fingerprint() -> str:
    """Hash of the code and the data manifest: a change to either means the outputs must be rebuilt."""
    h = hashlib.sha256()
    for path in sorted([*(ROOT / "tasks").glob("*.py"), *(ROOT / "royale").glob("*.py"), DATA / "manifest.json"]):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def is_complete() -> bool:
    try:
        return json.loads(MARKER.read_text()).get("fingerprint") == fingerprint()
    except (OSError, ValueError):
        return False


@contextlib.contextmanager
def build_lock():
    """One build at a time, across sessions (threads) and processes. Falls back to a thread lock without fcntl."""
    OUTPUTS.mkdir(exist_ok=True)
    try:
        import fcntl
    except ImportError:  # Windows: one process runs the app, so a thread lock is enough
        with _THREAD_LOCK:
            yield
        return
    with open(OUTPUTS / ".build.lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run(quiet: bool = True, force: bool = True) -> bool:
    """Build every output. With force=False, return at once if a complete, current build already exists.
    Returns True if this call built the outputs."""
    with build_lock():
        if not force and is_complete():
            return False
        MARKER.unlink(missing_ok=True)
        for name in ORDER:
            started = time.perf_counter()
            module = importlib.import_module(f"tasks.{name}")
            argv, sys.argv = sys.argv, [name]  # default analysis window for every task
            try:
                if quiet:
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.main()
                else:
                    module.main()
            finally:
                sys.argv = argv
            print(f"  {name:<22} {time.perf_counter() - started:5.1f} s", flush=True)
        tmp = MARKER.with_name(f".{MARKER.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"fingerprint": fingerprint(), "finished": time.strftime("%Y-%m-%d %H:%M:%S")}))
        os.replace(tmp, MARKER)
        return True


if __name__ == "__main__":
    t = time.perf_counter()
    run(quiet="-v" not in sys.argv, force=True)
    print(f"All outputs rebuilt in {time.perf_counter() - t:.0f} s")
