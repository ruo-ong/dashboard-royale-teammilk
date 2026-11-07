"""Where things live. Every path in the project is built from ROOT, so code runs from any folder."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


def _discover_tables() -> dict[str, Path]:
    """Map table name -> parquet path, e.g. 'machine_day' -> data/2_machine_decision/machine_day.parquet."""
    tables: dict[str, Path] = {}
    for path in sorted(DATA.rglob("*.parquet")):
        name = path.stem
        if name in tables:
            raise RuntimeError(f"Two tables share the name {name!r}: {tables[name]} and {path}")
        tables[name] = path
    return tables


TABLES = _discover_tables()


def table_path(name: str) -> Path:
    try:
        return TABLES[name]
    except KeyError:
        raise KeyError(f"Unknown table {name!r}. Known tables: {', '.join(sorted(TABLES))}") from None
