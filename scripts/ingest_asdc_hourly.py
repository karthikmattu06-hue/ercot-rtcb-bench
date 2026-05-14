#!/usr/bin/env python3
"""Ingest np4-212-cd ASDC hourly curves from ERCOT MISAPP.

Usage:
    python scripts/ingest_asdc_hourly.py --start 2025-12-05 --end 2026-04-01
    python scripts/ingest_asdc_hourly.py --start 2026-01-15 --end 2026-01-16 --force
    python scripts/ingest_asdc_hourly.py --date 2026-02-01

Output:
    data/processed/v0.1/asdc_hourly/<YYYY-MM-DD>.parquet
    Raw zips cached at data/raw/asdc_hourly/<NP4-212-CD_YYYYMMDD.zip>
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

REPO_ROOT = Path(__file__).parent.parent
OUT_DIR = REPO_ROOT / "data" / "processed" / "v0.1" / "asdc_hourly"
CACHE_DIR = REPO_ROOT / "data" / "raw" / "asdc_hourly"

V01_START = date(2025, 12, 5)
V01_END = date(2026, 4, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest np4-212-cd ASDC hourly curves")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", help="Single operating date YYYY-MM-DD")
    group.add_argument(
        "--start",
        help=f"Start date (inclusive). Default: {V01_START}",
    )
    parser.add_argument(
        "--end",
        default=V01_END.isoformat(),
        help=f"End date (exclusive). Default: {V01_END}",
    )
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    parser.add_argument(
        "--out-dir", default=str(OUT_DIR), help="Output Parquet directory"
    )
    parser.add_argument(
        "--cache-dir", default=str(CACHE_DIR), help="Raw zip cache directory"
    )
    args = parser.parse_args()

    from ercot_rtcb_bench.data.asdc import ingest_asdc_hourly_date, ingest_asdc_hourly_range

    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)

    if args.date:
        d = date.fromisoformat(args.date)
        try:
            path = ingest_asdc_hourly_date(d, out_dir, cache_dir, force=args.force)
            print(f"OK  {path}")
            return 0
        except Exception as e:
            print(f"FAIL {d}: {e}", file=sys.stderr)
            return 1

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    results = ingest_asdc_hourly_range(start, end, out_dir, cache_dir, force=args.force)

    n_ok = sum(v for v in results.values())
    n_fail = len(results) - n_ok
    print(f"\nIngested {n_ok}/{len(results)} dates ({n_fail} failures)")
    for d, ok in sorted(results.items()):
        if not ok:
            print(f"  FAIL {d}", file=sys.stderr)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
