"""Create the schema and load fully synthetic RCM claims data.

Usage (from the repo root):
    backend/.venv/Scripts/python scripts/seed_database.py --reset
    backend/.venv/Scripts/python scripts/seed_database.py --reset --as-of 2026-10-06 --months 18 --seed 42

Uses DATABASE_URL from backend/.env (SQLite at backend/data/rcm.db by default).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.analytics.snapshots import refresh_kpi_snapshots  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.init_db import create_schema, load_rows  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.db.synthetic import generate  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    p.add_argument("--months", type=int, default=18)
    p.add_argument("--monthly-claims", type=int, default=650)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    configure_logging("INFO")
    engine = get_engine()
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    create_schema(engine, reset=args.reset)
    data = generate(as_of=args.as_of, months=args.months, base_monthly_claims=args.monthly_claims, seed=args.seed)
    counts = load_rows(engine, data)
    print("Loaded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    n = refresh_kpi_snapshots()
    print(f"KPI snapshots computed for {n} months")


if __name__ == "__main__":
    main()
