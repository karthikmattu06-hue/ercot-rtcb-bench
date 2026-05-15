"""Validate NPRR1268 ASDC oracle reconstruction over the v0.1 window.

Usage:
    python scripts/validate_asdc_oracle_window.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--he HE]

Defaults to the full v0.1 window (2025-12-01 to 2026-03-28) at HE13.
Exits with code 1 if any product's mean error exceeds $0.10/MW-h.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ercot_rtcb_bench.data.asdc import reconstruct_per_product_asdc
from ercot_rtcb_bench.data.io import load_as_plan, load_asdc_hourly

MU, SIGMA, VOLL = 675.0, 1524.0, 5000.0
PRODUCTS = ["regup", "rrs", "ecrs", "nspin"]
THRESHOLD = 0.10  # $/MW-h


def run(start: date, end: date, he: int) -> bool:
    results: dict[str, dict] = {
        p: {"errors": [], "mismatches": 0, "missing": 0} for p in PRODUCTS
    }
    days_run = 0
    d = start
    while d <= end:
        try:
            as_plan = load_as_plan(d, he)
        except (FileNotFoundError, KeyError):
            for p in PRODUCTS:
                results[p]["missing"] += 1
            d += timedelta(days=1)
            continue

        for prod in PRODUCTS:
            try:
                oracle = load_asdc_hourly(d, he, prod)
                recon = reconstruct_per_product_asdc(prod, MU, SIGMA, VOLL, as_plan)
                if len(oracle) != len(recon):
                    results[prod]["mismatches"] += 1
                    print(
                        f"MISMATCH {d} HE{he} {prod}: oracle={len(oracle)} recon={len(recon)}",
                        file=sys.stderr,
                    )
                else:
                    pe = np.abs(oracle[:, 1] - recon[:, 1]).mean()
                    results[prod]["errors"].append(pe)
            except (FileNotFoundError, KeyError):
                results[prod]["missing"] += 1

        days_run += 1
        d += timedelta(days=1)

    print(f"\nDays processed: {days_run}  (window {start} – {end}, HE{he})\n")
    all_pass = True
    for prod in PRODUCTS:
        errs = results[prod]["errors"]
        miss = results[prod]["missing"]
        mis = results[prod]["mismatches"]
        if not errs:
            print(f"{prod:8s}: no data  missing={miss}")
            continue
        mean_e = float(np.mean(errs))
        max_e = float(np.max(errs))
        n_pass = sum(e <= THRESHOLD for e in errs)
        ok = mean_e <= THRESHOLD
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(
            f"{prod:8s}: n={len(errs):3d}  mean=${mean_e:.4f}  max=${max_e:.4f}  "
            f"pass_rate={n_pass}/{len(errs)}  missing={miss}  mismatch={mis}  [{status}]"
        )

    if all_pass:
        print("\nAll products PASS ≤$0.10/MW-h.")
    else:
        print("\nOne or more products FAILED.", file=sys.stderr)
    return all_pass


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_date, default=date(2025, 12, 1))
    parser.add_argument("--end", type=_parse_date, default=date(2026, 3, 28))
    parser.add_argument("--he", type=int, default=13)
    args = parser.parse_args()

    ok = run(args.start, args.end, args.he)
    sys.exit(0 if ok else 1)
