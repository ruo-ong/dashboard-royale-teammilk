"""Every dashboard page renders without an exception (Streamlit's headless AppTest), for the full window and a sub-period."""
import pytest
from streamlit.testing.v1 import AppTest

from royale.outputs import output_path

PAGES = ["summary", "machines", "demand", "downtime", "players", "comps", "model", "plan", "methods"]
SCRIPT = """
import sys, datetime as dt
from pathlib import Path
root = Path(r"{root}")
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "dashboard"))
import streamlit as st
st.session_state.setdefault("date_range", ({start}, {end}))
st.session_state.setdefault("zones", {zones}); st.session_state.setdefault("banks", [])
from views import {page}
{page}.render()
"""


@pytest.fixture(scope="module", autouse=True)
def built():
    if not output_path("portfolio").exists():
        from tasks.run_all import run
        run()


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("window,zones", [(("dt.date(2025, 1, 1)", "dt.date(2025, 6, 30)"), []),
                                          (("dt.date(2025, 4, 1)", "dt.date(2025, 6, 30)"), ["Back Forty"])])
def test_page_renders(page, window, zones):
    from royale.paths import ROOT
    at = AppTest.from_string(SCRIPT.format(root=ROOT, page=page, start=window[0], end=window[1], zones=zones), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_app_entry_point_runs():
    from royale.paths import ROOT
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
