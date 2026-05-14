#!/usr/bin/env python3
"""MILP baseline smoke run: Feb 1-7, 2026 at HB_HUBAVG.

Runs both perfect-foresight and point-forecast baselines for a 100 MW / 400 MWh
BESS at HB_HUBAVG and prints a revenue summary.

Usage:
    python scripts/smoke_milp.py
    python scripts/smoke_milp.py --v01-dir ~/my-data/v0.1

Requires v0.1 data at data/processed/v0.1/ (or --v01-dir override).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_V01_DIR = REPO_ROOT / "data" / "processed" / "v0.1"

SMOKE_START = "2026-02-01 06:00"  # UTC (midnight CST)
SMOKE_END = "2026-02-08 06:00"    # 7 days
SETTLEMENT_POINT = "HB_HUBAVG"


def _load_months(data_dir: Path, months: list[str]) -> pd.DataFrame:
    frames = []
    for m in months:
        f = data_dir / f"{m}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
    if not frames:
        raise FileNotFoundError(f"No Parquet files found for {months} in {data_dir}")
    return pd.concat(frames, ignore_index=True)


def _window_slice(df: pd.DataFrame, ts_col: str = "timestamp_utc") -> pd.DataFrame:
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.set_index(ts_col).sort_index()
    mask = (df.index >= pd.Timestamp(SMOKE_START, tz="UTC")) & \
           (df.index < pd.Timestamp(SMOKE_END, tz="UTC"))
    return df.loc[mask]


_AS_PRODUCT_COL_MAP = {
    # v0.1 uppercase product names → canonical column names
    "REGUP": "mcpc_regup", "regup": "mcpc_regup",
    "REGDN": "mcpc_regdn", "regdn": "mcpc_regdn",
    "RRS":   "mcpc_rrs",   "rrs":   "mcpc_rrs",
    "ECRS":  "mcpc_ecrs",  "ecrs":  "mcpc_ecrs",
    "NSPIN": "mcpc_nspin", "nspin": "mcpc_nspin",
}


def _load_rt_prices(v01_dir: Path) -> pd.DataFrame:
    """Load rt_prices + as_clearing and join into a wide 5-min price DataFrame."""
    months = ["2026-01", "2026-02"]

    # LMP
    rt = _window_slice(
        _load_months(v01_dir / "rt_prices", months)
        .query("settlement_point == @SETTLEMENT_POINT")
    )[["lmp"]]

    # MCPCs (long → wide pivot)
    ac = _window_slice(_load_months(v01_dir / "as_clearing", months))
    if "as_product" in ac.columns and "mcpc" in ac.columns:
        ac["col"] = ac["as_product"].map(_AS_PRODUCT_COL_MAP)
        ac = ac.dropna(subset=["col"])
        ac_wide = ac.pivot_table(index="timestamp_utc", columns="col", values="mcpc", aggfunc="mean")
        ac_wide.index.name = "timestamp_utc"
        rt = rt.join(ac_wide, how="left")

    for col in ["mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]:
        if col not in rt.columns:
            rt[col] = 0.0

    # Forward-fill MCPCs (SCED event-driven → fill forward for LP intervals)
    rt[["mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]] = (
        rt[["mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]]
        .ffill().fillna(0.0)
    )
    # Clip negative MCPCs to 0 (float noise; see validate.py MCPC_NEGATIVE_TOLERANCE)
    for col in ["mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]:
        rt[col] = rt[col].clip(lower=0.0)

    return rt.dropna(subset=["lmp"])


_V01_DAM_COL_RENAMES = {
    # v0.1 uses "dam_mcpc_*" prefix; canonical schema uses "mcpc_*" (ADR 0004)
    "dam_mcpc_regup": "mcpc_regup",
    "dam_mcpc_regdn": "mcpc_regdn",
    "dam_mcpc_rrs": "mcpc_rrs",
    "dam_mcpc_ecrs": "mcpc_ecrs",
    "dam_mcpc_nspin": "mcpc_nspin_online",  # v0.1 has combined; treat as online
}


def _load_dam_prices(v01_dir: Path) -> pd.DataFrame:
    months = ["2026-01", "2026-02"]
    df = _load_months(v01_dir / "dam_prices", months)
    if "settlement_point" in df.columns:
        df = df[df["settlement_point"] == SETTLEMENT_POINT]
    # Normalize v0.1 column names to canonical schema
    df = df.rename(columns=_V01_DAM_COL_RENAMES)
    # Add mcpc_nspin_offline as zero if absent (BESS uses online by default per ADR 0004)
    if "mcpc_nspin_offline" not in df.columns:
        df["mcpc_nspin_offline"] = 0.0
    return _window_slice(df)


def _print_summary(tag: str, result) -> None:
    disp = result.dispatch
    print(f"\n{'─'*60}")
    print(f"  {tag}")
    print(f"{'─'*60}")
    print(f"  Solver:          {result.solution.solver} ({result.solution.status})")
    print(f"  Intervals:       {len(disp):,}")
    print(f"  Revenue (total): ${result.revenue_total:>12,.2f}")
    print(f"  Revenue (energy):${result.revenue_energy:>12,.2f}")
    print(f"  Revenue (AS):    ${result.revenue_as:>12,.2f}")
    print(f"  Avg discharge:   {disp['discharge_mw'].mean():.2f} MW")
    print(f"  Avg charge:      {disp['charge_mw'].mean():.2f} MW")
    print(f"  Avg SoC:         {disp['soc_frac'].mean():.1%}")
    print(f"  SoC range:       [{disp['soc_frac'].min():.1%}, {disp['soc_frac'].max():.1%}]")
    print(f"  Avg RegUp award: {disp['award_regup_mw'].mean():.2f} MW")
    print(f"  Avg NonSpin awd: {disp['award_nspin_mw'].mean():.2f} MW")
    print(f"{'─'*60}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MILP baseline smoke run (Feb 1-7, 2026)")
    parser.add_argument(
        "--v01-dir",
        default=str(DEFAULT_V01_DIR),
        help=f"Path to v0.1 processed Parquet directory (default: {DEFAULT_V01_DIR})",
    )
    parser.add_argument(
        "--skip-pf", action="store_true",
        help="Skip perfect-foresight (run only point-forecast)",
    )
    args = parser.parse_args()

    v01_dir = Path(args.v01_dir)
    if not v01_dir.exists():
        print(f"ERROR: v0.1 data not found at {v01_dir}", file=sys.stderr)
        print("Run scripts/build_v0_1.py first, or pass --v01-dir.", file=sys.stderr)
        return 1

    from ercot_rtcb_bench.methods.battery import BESSParams
    from ercot_rtcb_bench.methods.perfect_foresight import perfect_foresight
    from ercot_rtcb_bench.methods.point_forecast import point_forecast

    bess = BESSParams.default_100mw_4hr(resource_name="BATT_BENCH_HUBAVG")

    print(f"\nBESS: {bess.power_mw:.0f} MW / {bess.energy_mwh:.0f} MWh, "
          f"RTE={bess.rte:.0%}, node={SETTLEMENT_POINT}")
    print(f"Window: {SMOKE_START} → {SMOKE_END} UTC (7 days)")

    logger.info("Loading RT prices...")
    rt_prices = _load_rt_prices(v01_dir)
    logger.info("RT prices: %d intervals", len(rt_prices))

    if not args.skip_pf:
        logger.info("Running perfect-foresight LP...")
        pf_result = perfect_foresight(bess, rt_prices)
        _print_summary("PERFECT FORESIGHT (upper bound)", pf_result)

    logger.info("Loading DAM prices...")
    try:
        dam_prices = _load_dam_prices(v01_dir)
        logger.info("DAM prices: %d hourly intervals", len(dam_prices))
    except FileNotFoundError as e:
        logger.warning("DAM prices not found (%s); skipping point-forecast", e)
        dam_prices = None

    if dam_prices is not None and not dam_prices.empty:
        logger.info("Running point-forecast LP...")
        pfcast_result = point_forecast(bess, rt_prices, dam_prices)
        _print_summary("POINT FORECAST (DAM prices)", pfcast_result)

        if not args.skip_pf:
            ratio = pfcast_result.revenue_total / pf_result.revenue_total
            print(f"\n  Point-forecast captures {ratio:.1%} of perfect-foresight revenue")

    return 0


if __name__ == "__main__":
    sys.exit(main())
