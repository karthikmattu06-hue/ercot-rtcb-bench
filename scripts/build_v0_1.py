#!/usr/bin/env python3
"""Build the canonical v0.1 Parquet tables and run validation.

Reads from ~/hybridbid/ (read-only) and writes to data/processed/v0.1/.
Also writes validation report to data/validation/.

Run from the repo root:
    python scripts/build_v0_1.py

Environment:
    HYBRIDBID_DIR  — path to hybridbid repo root (default: ~/hybridbid)
    V01_OUT_DIR    — output directory (default: data/processed/v0.1)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ercot_rtcb_bench.data.transform import run_all_transforms
from ercot_rtcb_bench.data.validate import run_validation, write_validation_report

HYBRIDBID_DIR = Path(os.environ.get("HYBRIDBID_DIR", Path.home() / "hybridbid"))
V01_OUT_DIR = Path(os.environ.get("V01_OUT_DIR", REPO_ROOT / "data" / "processed" / "v0.1"))
VALIDATION_DIR = REPO_ROOT / "data" / "validation"


def main() -> int:
    if not HYBRIDBID_DIR.exists():
        logger.error("HYBRIDBID_DIR not found: %s", HYBRIDBID_DIR)
        return 1

    logger.info("Source: %s", HYBRIDBID_DIR)
    logger.info("Output: %s", V01_OUT_DIR)

    V01_OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_all_transforms(HYBRIDBID_DIR, V01_OUT_DIR)

    import pandas as pd
    from ercot_rtcb_bench.markets.rtcb import RTCB_LAUNCH_UTC, V01_END_UTC

    logger.info("Running validation...")
    report = run_validation(
        V01_OUT_DIR,
        version="v0.1",
        dataset_start=pd.Timestamp(RTCB_LAUNCH_UTC),
        dataset_end=pd.Timestamp(V01_END_UTC),
        # sced_mcpc raw data ends Mar 21; as_clearing coverage is validated to that date
        as_clearing_end=pd.Timestamp("2026-03-22", tz="UTC"),
    )
    write_validation_report(report, VALIDATION_DIR)

    if not report.overall_passed:
        logger.error("Validation FAILED. See data/validation/ for details.")
        for name, t in report.tables.items():
            if not t.passed:
                logger.error("  %s: %s", name, t.bounds_errors + t.schema_errors)
        return 1

    logger.info("v0.1 build complete. All validation gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
