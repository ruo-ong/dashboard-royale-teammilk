"""Command-line date window shared by every task script:  python -m tasks.a2_exposure --start 2025-04-01 --end 2025-06-30"""
import argparse

DEFAULT_START = "2025-01-01"
DEFAULT_END = "2025-06-30"


def window_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--start", default=DEFAULT_START, help="first gaming date, inclusive (default %(default)s)")
    parser.add_argument("--end", default=DEFAULT_END, help="last gaming date, inclusive (default %(default)s)")
    args = parser.parse_args()
    print(f"Analysis window: {args.start} to {args.end}")
    return args
