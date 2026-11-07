"""The Gilded Ace floor performance review, version 2: the report plus the machine estimator.

Run from the repository folder:   streamlit run dashboard/app_v2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shell  # noqa: E402

shell.run(include_estimator=True)
