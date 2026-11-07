"""The Gilded Ace floor performance review (with the machine estimator).

Run from the repository folder:   streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shell  # noqa: E402

shell.run()
