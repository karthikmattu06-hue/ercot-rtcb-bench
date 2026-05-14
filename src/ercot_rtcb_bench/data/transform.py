"""Transform HybridBid source data into canonical v0.1 Parquet tables.

Reads from the read-only HybridBid source directory and writes canonical
v0.1 tables to data/processed/v0.1/ in the benchmark repo.

Source → canonical table mapping:
  hybridbid/data/processed/energy_prices/  → rt_prices/  (filter post-RTC+B)
  hybridbid/data/processed/as_prices/      → as_clearing/, dam_prices/
  hybridbid/data/processed/system_conditions/ → system_conditions/
  hybridbid/data/raw/sced_mcpc/            → as_clearing/ (raw SCED MCPCs)

Key design decisions:
  - All timestamps in UTC (source already uses UTC index named timestamp_utc).
  - Post-RTC+B filter: keep rows where is_post_rtcb == True AND
    timestamp_utc >= RTCB_LAUNCH_UTC (2025-12-05 06:00 UTC).
  - as_clearing is pivoted from wide (one row per timestamp) to long
    (one row per timestamp × as_product).
  - RT LMP settlement point is HB_HUBAVG for v0.1; multi-SP support is v1.0.
  - sced_mcpc is preferred over processed as_prices RT columns because it is
    the unmodified ERCOT source with SCED-exact timestamps.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ercot_rtcb_bench.markets.rtcb import RTCB_LAUNCH_UTC, V01_END_UTC

logger = logging.getLogger(__name__)

# ── Column rename maps ────────────────────────────────────────────────────────

# hybridbid as_prices RT columns → canonical AS product names
RT_MCPC_COL_MAP = {
    "rt_mcpc_regup": "REGUP",
    "rt_mcpc_regdn": "REGDN",
    "rt_mcpc_rrs": "RRS",
    "rt_mcpc_ecrs": "ECRS",
    "rt_mcpc_nsrs": "NSPIN",
}

DAM_AS_COL_MAP = {
    "dam_as_regup": "dam_mcpc_regup",
    "dam_as_regdn": "dam_mcpc_regdn",
    "dam_as_rrs": "dam_mcpc_rrs",
    "dam_as_ecrs": "dam_mcpc_ecrs",
    "dam_as_nsrs": "dam_mcpc_nspin",
}


def _load_processed_months(
    source_dir: Path,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> pd.DataFrame:
    """Load and concatenate monthly Parquet files covering [start_utc, end_utc)."""
    months = pd.period_range(start=start_utc.to_period("M"), end=end_utc.to_period("M"))
    frames: list[pd.DataFrame] = []
    for period in months:
        path = source_dir / f"{period}.parquet"
        if not path.exists():
            logger.warning("Missing source file: %s", path)
            continue
        df = pd.read_parquet(path)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No source files found in {source_dir} for requested range")
    combined = pd.concat(frames)
    combined = combined[
        (combined.index >= start_utc) & (combined.index < end_utc)
    ]
    combined = combined[combined.get("is_post_rtcb", True) == True]  # noqa: E712
    return combined


def transform_rt_prices(source_dir: Path, out_dir: Path) -> None:
    """Build rt_prices/ from hybridbid processed energy_prices.

    Output schema (per row):
        timestamp_utc  settlement_point  settlement_point_type  lmp  is_post_rtcb
    One file per month: rt_prices/2025-12.parquet, rt_prices/2026-01.parquet, ...
    """
    start = pd.Timestamp(RTCB_LAUNCH_UTC)
    end = pd.Timestamp(V01_END_UTC)

    df = _load_processed_months(source_dir / "energy_prices", start, end)
    df = df.reset_index()  # timestamp_utc becomes column
    df = df.rename(columns={"rt_lmp": "lmp"})
    df["settlement_point"] = "HB_HUBAVG"
    df["settlement_point_type"] = "Trading Hub"
    df = df[["timestamp_utc", "settlement_point", "settlement_point_type", "lmp", "is_post_rtcb"]]

    out_path = out_dir / "rt_prices"
    out_path.mkdir(parents=True, exist_ok=True)

    for period, group in df.groupby(df["timestamp_utc"].dt.to_period("M")):
        out_file = out_path / f"{period}.parquet"
        group.to_parquet(out_file, index=False, compression="snappy")
        logger.info("  wrote %s (%d rows)", out_file.name, len(group))


def transform_as_clearing(sced_mcpc_dir: Path, out_dir: Path) -> None:
    """Build as_clearing/ from raw sced_mcpc daily Parquet files.

    Reads raw SCED MCPC files, converts to UTC, rounds to nearest 5-min,
    pivots to long format (one row per timestamp × as_product).

    Output schema (per row):
        timestamp_utc  as_product  mcpc  is_post_rtcb
    """
    start = pd.Timestamp(RTCB_LAUNCH_UTC)
    end = pd.Timestamp(V01_END_UTC)

    # Load all sced_mcpc daily files that overlap the window
    # File naming: YYYY-MM-DD.parquet (CT day), timestamps are UTC
    frames: list[pd.DataFrame] = []
    for f in sorted(sced_mcpc_dir.glob("*.parquet")):
        try:
            file_date = pd.Timestamp(f.stem).tz_localize("UTC")
        except Exception:
            continue
        # File covers CT day file_date, so UTC range is ~(file_date+6h) to ~(file_date+30h)
        # Include a buffer: load if file_date is within [start-1d, end]
        if file_date < start - pd.Timedelta(days=1) or file_date >= end:
            continue
        df = pd.read_parquet(f)
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"No sced_mcpc files found in {sced_mcpc_dir}")

    raw = pd.concat(frames, ignore_index=True)

    # Rename to canonical column names
    raw = raw.rename(columns={"sced_timestamp": "timestamp_utc", "as_type": "as_product"})

    # Round irregular SCED timestamps to nearest 5-minute boundary
    raw["timestamp_utc"] = raw["timestamp_utc"].dt.round("5min")

    # Filter to window
    raw = raw[(raw["timestamp_utc"] >= start) & (raw["timestamp_utc"] < end)]

    # Aggregate: multiple SCED runs can map to the same 5-min bucket after rounding.
    # Take the last value (most recent SCED run within the 5-min window).
    raw = (
        raw.sort_values("timestamp_utc")
        .groupby(["timestamp_utc", "as_product"], as_index=False)["mcpc"]
        .last()
    )

    raw["is_post_rtcb"] = True

    out_path = out_dir / "as_clearing"
    out_path.mkdir(parents=True, exist_ok=True)

    for period, group in raw.groupby(raw["timestamp_utc"].dt.to_period("M")):
        out_file = out_path / f"{period}.parquet"
        group.to_parquet(out_file, index=False, compression="snappy")
        logger.info("  wrote %s (%d rows)", out_file.name, len(group))


def transform_dam_prices(source_dir: Path, out_dir: Path) -> None:
    """Build dam_prices/ from hybridbid processed as_prices + energy_prices.

    Merges the hourly DAM AS MCPCs with the hourly DAM SPP.
    Note: DAM prices are hourly; the source 5-min grid is downsampled to
    the first row of each hour (they are constant within each hour by design).

    Output schema (per row):
        timestamp_utc  settlement_point  dam_spp
        dam_mcpc_regup  dam_mcpc_regdn  dam_mcpc_rrs  dam_mcpc_ecrs  dam_mcpc_nspin
        is_post_rtcb
    """
    start = pd.Timestamp(RTCB_LAUNCH_UTC)
    end = pd.Timestamp(V01_END_UTC)

    as_df = _load_processed_months(source_dir / "as_prices", start, end)
    en_df = _load_processed_months(source_dir / "energy_prices", start, end)

    # Extract DAM columns and downsample to hourly (first value per hour is the DAM value)
    dam_as = (
        as_df[[c for c in as_df.columns if c.startswith("dam_as_")]]
        .rename(columns=DAM_AS_COL_MAP)
        .resample("h")
        .first()
        .dropna(how="all")
    )
    dam_en = (
        en_df[["dam_spp"]]
        .resample("h")
        .first()
        .dropna(how="all")
    )

    combined = dam_as.join(dam_en, how="inner")
    combined = combined.reset_index()
    combined["settlement_point"] = "HB_HUBAVG"
    combined["is_post_rtcb"] = True

    cols = [
        "timestamp_utc", "settlement_point", "dam_spp",
        "dam_mcpc_regup", "dam_mcpc_regdn", "dam_mcpc_rrs",
        "dam_mcpc_ecrs", "dam_mcpc_nspin", "is_post_rtcb",
    ]
    combined = combined[cols]

    out_path = out_dir / "dam_prices"
    out_path.mkdir(parents=True, exist_ok=True)

    for period, group in combined.groupby(combined["timestamp_utc"].dt.to_period("M")):
        out_file = out_path / f"{period}.parquet"
        group.to_parquet(out_file, index=False, compression="snappy")
        logger.info("  wrote %s (%d rows)", out_file.name, len(group))


def transform_system_conditions(source_dir: Path, out_dir: Path) -> None:
    """Build system_conditions/ from hybridbid processed system_conditions.

    No structural change — just filter to post-RTC+B and write per-month.
    """
    start = pd.Timestamp(RTCB_LAUNCH_UTC)
    end = pd.Timestamp(V01_END_UTC)

    df = _load_processed_months(source_dir / "system_conditions", start, end)
    df = df.reset_index()

    out_path = out_dir / "system_conditions"
    out_path.mkdir(parents=True, exist_ok=True)

    for period, group in df.groupby(df["timestamp_utc"].dt.to_period("M")):
        out_file = out_path / f"{period}.parquet"
        group.to_parquet(out_file, index=False, compression="snappy")
        logger.info("  wrote %s (%d rows)", out_file.name, len(group))


def run_all_transforms(
    hybridbid_dir: Path,
    out_dir: Path,
) -> None:
    """Run all v0.1 transforms. hybridbid_dir is treated as read-only."""
    processed_src = hybridbid_dir / "data" / "processed"
    sced_src = hybridbid_dir / "data" / "raw" / "sced_mcpc"

    logger.info("Transforming rt_prices...")
    transform_rt_prices(processed_src, out_dir)

    logger.info("Transforming as_clearing...")
    transform_as_clearing(sced_src, out_dir)

    logger.info("Transforming dam_prices...")
    transform_dam_prices(processed_src, out_dir)

    logger.info("Transforming system_conditions...")
    transform_system_conditions(processed_src, out_dir)

    logger.info("All transforms complete → %s", out_dir)
