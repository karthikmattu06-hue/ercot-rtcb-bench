#!/usr/bin/env python3
"""Parse AORDC Regression Fit Parameters xlsx into ASDCParameters Parquet.

Usage:
    python scripts/ingest_asdc_params.py --xlsx path/to/aordc_params.xlsx

The xlsx is the "AORDC Regression Fit Parameters for RTC+B Go-Live" file
published on the ERCOT RTCBTF Key Documents page on 2025-09-30.
Download it manually from:
  https://www.ercot.com/calendar/2025/9/30/249105

Output:
    data/processed/v0.1/asdc_params.parquet
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
DEFAULT_OUT = REPO_ROOT / "data" / "processed" / "v0.1" / "asdc_params.parquet"

AORDC_SOURCE_URL = "https://www.ercot.com/calendar/2025/9/30/249105"
AORDC_DOC_REVISION = "RTC+B go-live 2025-09-30"
AORDC_EFFECTIVE_DATE = date(2025, 12, 5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse AORDC Regression Fit Parameters xlsx → ASDCParameters Parquet"
    )
    parser.add_argument(
        "--xlsx",
        required=True,
        help="Path to the AORDC Regression Fit Parameters xlsx file",
    )
    parser.add_argument(
        "--effective-date",
        default=AORDC_EFFECTIVE_DATE.isoformat(),
        help=f"Effective date for these parameters (default: {AORDC_EFFECTIVE_DATE})",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"Output Parquet path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--source-url",
        default=AORDC_SOURCE_URL,
        help="Source URL to record in ASDCParameters",
    )
    parser.add_argument(
        "--source-doc-revision",
        default=AORDC_DOC_REVISION,
        help="Source doc revision string",
    )
    args = parser.parse_args()

    from ercot_rtcb_bench.data.asdc import parse_aordc_xlsx, save_asdc_params

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERROR: xlsx not found: {xlsx_path}", file=sys.stderr)
        return 1

    effective_date = date.fromisoformat(args.effective_date)
    out_path = Path(args.out)

    try:
        params = parse_aordc_xlsx(
            xlsx_path,
            effective_date=effective_date,
            source_url=args.source_url,
            source_doc_revision=args.source_doc_revision,
        )
        save_asdc_params(params, out_path)
        print(f"Wrote {len(params)} ASDCParameters records → {out_path}")
        for p in params:
            print(f"  {p.as_product.value:8s}  mu={p.mu:.1f}  sigma={p.sigma:.1f}  "
                  f"w30={p.mix_weight_30min:.3f}  w60={p.mix_weight_60min:.3f}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
