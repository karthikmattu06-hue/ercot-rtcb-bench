"""I/O helpers for loading processed v0.1 data tables.

AS Plan: monthly Parquets at <repo>/data/processed/v0.1/as_plan/YYYY-MM.parquet
ASDC Hourly: per-date Parquets at BENCH_DATA_ROOT/asdc_hourly/YYYY-MM-DD.parquet
             Default BENCH_DATA_ROOT: ~/hybridbid-bench-data/v0.1
             Override: set env var BENCH_DATA_ROOT
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ── Default paths ─────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_AS_PLAN_DIR = _REPO_ROOT / "data" / "processed" / "v0.1" / "as_plan"

_DEFAULT_ASDC_DATA_ROOT = Path(
    os.environ.get("BENCH_DATA_ROOT", Path.home() / "hybridbid-bench-data" / "v0.1")
) / "asdc_hourly"


# ── Public helpers ────────────────────────────────────────────────────────────


def load_as_plan(
    operating_date: date,
    hour_ending: int,
    as_plan_dir: Path | None = None,
) -> dict[str, float]:
    """Return AS Plan quantities for a single (operating_date, hour_ending).

    Raises KeyError if the row is not found.
    """
    parquet_dir = as_plan_dir or _DEFAULT_AS_PLAN_DIR
    month_key = operating_date.strftime("%Y-%m")
    parquet_path = parquet_dir / f"{month_key}.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"AS Plan parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    row = df[(df["operating_date"] == operating_date) & (df["hour_ending"] == hour_ending)]
    if row.empty:
        raise KeyError(
            f"No AS Plan row for operating_date={operating_date}, hour_ending={hour_ending}"
        )
    rec = row.iloc[0]
    return {
        "rureq":    float(rec["rureq"]),
        "regdnreq": float(rec["regdnreq"]),
        "rrsreq":   float(rec["rrsreq"]),
        "ecrsreq":  float(rec["ecrsreq"]),
        "nspinreq": float(rec["nspinreq"]),
    }


def load_asdc_hourly(
    operating_date: date,
    hour_ending: int,
    product: str,
    asdc_data_root: Path | None = None,
) -> np.ndarray:
    """Return oracle ASDC breakpoints for (operating_date, hour_ending, product).

    Returns array of shape (N, 2): columns [breakpoint_mw, breakpoint_price],
    sorted by segment_index.

    Raises FileNotFoundError / KeyError if the data is missing.
    """
    data_root = asdc_data_root or _DEFAULT_ASDC_DATA_ROOT
    parquet_path = data_root / f"{operating_date.isoformat()}.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"ASDC hourly parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    mask = (
        (df["operating_date"] == operating_date)
        & (df["hour_ending"] == hour_ending)
        & (df["as_product"] == product)
    )
    sub = df[mask].sort_values("segment_index")
    if sub.empty:
        raise KeyError(
            f"No ASDC rows for {operating_date} HE{hour_ending} {product}"
        )
    return sub[["breakpoint_mw", "breakpoint_price"]].to_numpy(dtype=float)
