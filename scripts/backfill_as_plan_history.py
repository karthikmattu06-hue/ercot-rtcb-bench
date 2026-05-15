#!/usr/bin/env python3
"""Backfill np4-33-CD AS Plan data via ERCOT Public Data API archive.

MISAPP retains only ~31 days of rolling publications. For the full v0.1 window
(Dec 5, 2025 – Mar 31, 2026) we fetch from the ERCOT Public Data API archive.

Each MISAPP/archive publication covers 7 operating days from the publication
date. The backfill downloads all publications that cover the target window,
parses them, deduplicates by (operating_date, hour_ending) to handle overlapping
7-day windows, and writes monthly Parquet files.

Authentication requires a .env file (or environment variables):
    ERCOT_API_USERNAME               — ERCOT API account username
    ERCOT_API_PASSWORD               — ERCOT API account password
    ERCOT_PUBLIC_API_SUBSCRIPTION_KEY — subscription key from developer portal

Usage:
    # Dry-run: list which monthly files are missing
    python scripts/backfill_as_plan_history.py --dry-run

    # Full v0.1 backfill (default window Dec 5, 2025 – Mar 31, 2026)
    python scripts/backfill_as_plan_history.py

    # Smaller window for testing
    python scripts/backfill_as_plan_history.py --date-from 2026-03-01 --date-to 2026-03-03

    # Force re-download (overwrite existing monthly Parquets)
    python scripts/backfill_as_plan_history.py --force

Output:
    data/processed/v0.1/as_plan/<YYYY-MM>.parquet  (one per calendar month)

References:
    - np4-33-CD Report Type ID = 12316 (empirically determined 2026-05-14)
    - ADR 0005: two-surface ingest pattern
    - https://www.ercot.com/mp/data-products/data-product-details?id=NP4-33-CD
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "data" / "processed" / "v0.1" / "as_plan"

V01_START = date(2025, 12, 5)
V01_END = date(2026, 3, 31)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.debug("Loaded .env from %s", env_path)
    except ImportError:
        pass


def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        logger.error("Missing required environment variable: %s", key)
        logger.error("Set it in .env or export it before running this script.")
        sys.exit(1)
    return val


def _missing_months(out_dir: Path, date_from: date, date_to: date) -> list[str]:
    existing = {f.stem for f in out_dir.glob("???-??.parquet")}
    needed = {
        d.strftime("%Y-%m")
        for d in pd.date_range(start=date_from, end=date_to, freq="MS")
    }
    return sorted(needed - existing)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill np4-33-CD AS Plan data for the v0.1 window"
    )
    parser.add_argument(
        "--date-from",
        default=V01_START.isoformat(),
        help=f"Start date inclusive (default: {V01_START})",
    )
    parser.add_argument(
        "--date-to",
        default=V01_END.isoformat(),
        help=f"End date inclusive (default: {V01_END})",
    )
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="Output directory for monthly Parquet files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and overwrite existing monthly Parquet files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List missing months without downloading",
    )
    args = parser.parse_args()

    _load_env()

    out_dir = Path(args.out_dir)
    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)

    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        missing = _missing_months(out_dir, date_from, date_to)
        if missing:
            print(f"Missing {len(missing)} monthly Parquet(s):")
            for m in missing:
                print(f"  {m}")
        else:
            print("All monthly Parquet files already present.")
        return 0

    username = _require_env("ERCOT_API_USERNAME")
    password = _require_env("ERCOT_API_PASSWORD")
    sub_key = _require_env("ERCOT_PUBLIC_API_SUBSCRIPTION_KEY")

    from ercot_rtcb_bench.data.as_plan import backfill_as_plan_history

    logger.info("Backfilling AS Plan: %s → %s", date_from, date_to)
    monthly_counts = backfill_as_plan_history(
        date_from=date_from,
        date_to=date_to,
        out_dir=out_dir,
        username=username,
        password=password,
        sub_key=sub_key,
        force=args.force,
    )

    total_rows = sum(monthly_counts.values())
    print(f"\nBackfill complete:")
    print(f"  {len(monthly_counts)} monthly Parquet(s) written, {total_rows} total rows")
    for month, count in sorted(monthly_counts.items()):
        print(f"  {month}: {count} rows")

    # Quick coverage check against expected 2,807 rows for full v0.1 window
    if date_from <= V01_START and date_to >= V01_END:
        expected = 2807
        pct = total_rows / expected * 100
        print(f"\nCoverage: {total_rows}/{expected} rows ({pct:.1f}%)")
        if pct < 99.0:
            print("WARNING: coverage below 99% gate", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
