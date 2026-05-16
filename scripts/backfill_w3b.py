#!/usr/bin/env python3
"""W3-B Task 0 — Data backfill and forecaster dataset assembly.

Two responsibilities:
1. Fetch missing data for Apr 16 – May 10, 2026 via ERCOT API (rt_lmp, dam_as,
   wind, solar, load, and SCED MCPC via NP6-332-CD) and cache to ~/hybridbid/data/raw/.
2. Assemble the consolidated forecaster dataset in data/processed/forecaster/:
     rt_prices/<YYYY-MM>.parquet     — 5-min RT prices (6 series)
     dam_prices/<YYYY-MM>.parquet    — hourly DAM prices (6 series)
     system_conditions/<YYYY-MM>.parquet — 5-min system conditions

Source priority:
  - Existing data in ~/hybridbid/data/processed/ (Jan 9 – Apr 15, 2026)
  - Newly fetched data (Apr 16 – May 10, 2026)

Data-quality gate:
  After assembly, emits a per-series gap + NaN report.  If any series has
  unexpected gaps > 2% or suspicious NaN clusters → prints HALT message and exits 1.

Usage:
    python scripts/backfill_w3b.py                     # full gap (Apr 16 – May 10)
    python scripts/backfill_w3b.py --start 2026-04-16 --end 2026-05-11
    python scripts/backfill_w3b.py --assemble-only     # skip fetch, just assemble
    python scripts/backfill_w3b.py --dry-run           # show what would be done

Environment (same as fetch_v1_0.sh):
    ERCOT_API_USERNAME
    ERCOT_API_PASSWORD
    ERCOT_PUBLIC_API_SUBSCRIPTION_KEY
    HYBRIDBID_DIR  (default: ~/hybridbid)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_w3b")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

HYBRIDBID_DIR = Path(os.environ.get("HYBRIDBID_DIR", Path.home() / "hybridbid"))
FC_DIR = REPO_ROOT / "data" / "processed" / "forecaster"

POOL_START = date(2026, 1, 9)
FETCH_END = date(2026, 5, 11)   # exclusive; covers through May 10 inclusive

# Columns to extract from hybridbid processed into forecaster dataset
_EP_RT_COLS = {"rt_lmp": "lmp"}
_EP_DAM_COLS = {"dam_spp": "dam_spp"}
_AS_RT_COLS = {
    "rt_mcpc_regup": "mcpc_regup",
    "rt_mcpc_regdn": "mcpc_regdn",
    "rt_mcpc_rrs": "mcpc_rrs",
    "rt_mcpc_ecrs": "mcpc_ecrs",
    "rt_mcpc_nsrs": "mcpc_nspin",
}
_AS_DAM_COLS = {
    "dam_as_regup": "dam_mcpc_regup",
    "dam_as_regdn": "dam_mcpc_regdn",
    "dam_as_rrs": "dam_mcpc_rrs",
    "dam_as_ecrs": "dam_mcpc_ecrs",
    "dam_as_nsrs": "dam_mcpc_nspin",
}
_SYS_COLS = ["total_load_mw", "wind_actual_mw", "solar_actual_mw", "net_load_mw"]

RT_PRICE_COLS = ["lmp", "mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]
DAM_PRICE_COLS = [
    "dam_spp", "dam_mcpc_regup", "dam_mcpc_regdn", "dam_mcpc_rrs",
    "dam_mcpc_ecrs", "dam_mcpc_nspin",
]


# ── Fetch layer ───────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env from hybridbid or repo root."""
    for env_path in [HYBRIDBID_DIR / ".env", REPO_ROOT / ".env"]:
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)
            logger.info("Loaded .env from %s", env_path)
            return
    logger.warning("No .env found; relying on environment variables")


def _get_api():
    from gridstatus.ercot_api.ercot_api import ErcotAPI
    api = ErcotAPI(sleep_seconds=2.0, max_retries=5)
    api.get_token()
    return api


def _with_retry(fn, *args, max_retries: int = 6, base_delay: float = 4.0, **kwargs):
    """Call fn with exponential backoff on 429/5xx; 429 is NOT missing data."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            is_rate = "429" in msg or "rate limit" in msg or "too many" in msg
            is_server = any(f"{c}" in msg for c in [500, 502, 503, 504])
            if (is_rate or is_server) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Attempt %d failed (%s). Retrying in %.0fs...", attempt + 1, e, delay
                )
                time.sleep(delay)
            else:
                raise


def fetch_rt_lmp(api, day: date) -> pd.DataFrame | None:
    """Fetch 5-min RT LMP for one day via get_lmp_by_settlement_point (NP6-788-CD)."""
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    df = _with_retry(api.get_lmp_by_settlement_point, date=start, end=end)
    if df is None or df.empty:
        return None
    # Filter to HB_HUBAVG (method returns all settlement points)
    loc_col = next((c for c in df.columns if "location" in c.lower()), None)
    if loc_col and "HB_HUBAVG" in df[loc_col].values:
        df = df[df[loc_col] == "HB_HUBAVG"].copy()
    return df


def fetch_sced_mcpc_api(token: str, sub_key: str, day: date) -> pd.DataFrame | None:
    """Fetch RT SCED MCPC via NP6-332-CD public API.

    Endpoint: rt_clear_price_cap_sced
    Fields: SCEDTimestamp (UTC), repeatHourFlag, ASType, MCPC
    Returns DataFrame with columns: sced_timestamp (UTC), as_type (str), mcpc (float).
    """
    import requests

    base_url = (
        "https://api.ercot.com/api/public-reports/np6-332-cd/rt_clear_price_cap_sced"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": sub_key,
    }

    # API uses UTC timestamps; cover the full UTC day + 1h buffer for timezone edge
    day_start = pd.Timestamp(day, tz="UTC")
    day_end = day_start + pd.Timedelta(hours=25)

    all_rows: list[list] = []
    fields: list[str] = []
    page = 1
    page_size = 5000  # Full day is ~1440 rows; one request typically sufficient

    while True:
        params = {
            "SCEDTimestampFrom": day_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "SCEDTimestampTo": day_end.strftime("%Y-%m-%dT%H:%M:%S"),
            "size": page_size,
            "page": page,
        }

        for attempt in range(6):
            try:
                resp = requests.get(base_url, headers=headers, params=params, timeout=60)
                if resp.status_code == 429:
                    delay = 4.0 * (2 ** attempt)
                    logger.warning("Rate limited (429). Retrying in %.0fs...", delay)
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt < 5:
                    delay = 4.0 * (2 ** attempt)
                    logger.warning("Request failed: %s. Retrying in %.0fs...", e, delay)
                    time.sleep(delay)
                else:
                    raise

        data = resp.json()
        if not fields:
            raw_fields = data.get("fields", [])
            # fields may be list of dicts or list of strings depending on API version
            fields = [f["name"] if isinstance(f, dict) else f for f in raw_fields]
        rows = data.get("data", [])
        all_rows.extend(rows)

        meta = data.get("_meta", {})
        total_pages = meta.get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(1.0)

    if not all_rows or not fields:
        return None

    df = pd.DataFrame(all_rows, columns=fields)

    # Normalize column names
    df = df.rename(columns={
        "SCEDTimestamp": "sced_timestamp",
        "ASType": "as_type",
        "MCPC": "mcpc",
        "repeatHourFlag": "repeated_hour_flag",
    })

    # Parse timestamp — API returns UTC strings without timezone suffix
    ts = pd.to_datetime(df["sced_timestamp"], utc=True, errors="coerce")
    df["sced_timestamp"] = ts

    # Normalize AS product names
    product_map = {
        "REGUP": "REGUP", "REGDN": "REGDN",
        "RRS": "RRS", "ECRS": "ECRS",
        "NSPIN": "NSPIN", "NSRS": "NSPIN",
    }
    df["as_type"] = df["as_type"].str.upper().str.strip().map(product_map).fillna(df["as_type"])
    df["mcpc"] = pd.to_numeric(df["mcpc"], errors="coerce")

    return df[["sced_timestamp", "as_type", "mcpc"]].dropna(subset=["sced_timestamp"])


def fetch_dam_spp(api, day: date) -> pd.DataFrame | None:
    """Fetch DAM settlement point price (HB_HUBAVG) via get_spp_day_ahead_hourly."""
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    df = _with_retry(api.get_spp_day_ahead_hourly, date=start, end=end)
    if df is None or df.empty:
        return None
    # Filter to hub average only
    if "Location" in df.columns and "HB_HUBAVG" in df["Location"].values:
        df = df[df["Location"] == "HB_HUBAVG"].copy()
    return df


def fetch_dam_as(api, day: date) -> pd.DataFrame | None:
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    return _with_retry(api.get_as_prices, date=start, end=end)


def fetch_wind(api, day: date) -> pd.DataFrame | None:
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    return _with_retry(api.get_wind_actual_and_forecast_hourly, date=start, end=end)


def fetch_solar(api, day: date) -> pd.DataFrame | None:
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    return _with_retry(api.get_solar_actual_and_forecast_hourly, date=start, end=end)


def fetch_load(api, day: date) -> pd.DataFrame | None:
    """Fetch system load via get_load_forecast_by_model (InUseFlag=True).

    Post-settlement actual load data lags ~60 days, so for recent dates we use the
    active model's forecast as the best available ex-ante proxy for actual load.
    """
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    df = _with_retry(api.get_load_forecast_by_model, date=start, end=end)
    if df is None or df.empty:
        return None
    if "In Use Flag" in df.columns:
        active = df[df["In Use Flag"] == True]
        if not active.empty:
            df = active
    return df


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _raw_cache(product: str, day: date) -> Path:
    raw_dir = HYBRIDBID_DIR / "data" / "raw" / product
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / f"{day.strftime('%Y-%m-%d')}.parquet"


def _fetch_one_day(
    product: str,
    day: date,
    api=None,
    token: str = "",
    sub_key: str = "",
    force: bool = False,
) -> bool:
    cache = _raw_cache(product, day)
    if cache.exists() and not force:
        return True

    logger.info("Fetching %s for %s...", product, day)
    try:
        if product == "rt_lmp":
            df = fetch_rt_lmp(api, day)
        elif product == "sced_mcpc":
            df = fetch_sced_mcpc_api(token, sub_key, day)
        elif product == "dam_spp":
            df = fetch_dam_spp(api, day)
        elif product == "dam_as":
            df = fetch_dam_as(api, day)
        elif product == "wind":
            df = fetch_wind(api, day)
        elif product == "solar":
            df = fetch_solar(api, day)
        elif product == "load_actual":
            df = fetch_load(api, day)
        else:
            raise ValueError(f"Unknown product: {product}")

        if df is None or df.empty:
            logger.warning("Empty result for %s / %s", product, day)
            return False

        df.to_parquet(cache, compression="snappy")
        logger.info("  Saved %s rows → %s", len(df), cache.name)
        return True

    except Exception as e:
        logger.error("Failed %s / %s: %s", product, day, e)
        return False


def run_fetch(
    start: date,
    end_excl: date,
    force: bool = False,
) -> dict:
    """Fetch all products for [start, end_excl) date range."""
    _load_dotenv()

    username = os.environ.get("ERCOT_API_USERNAME", "")
    password = os.environ.get("ERCOT_API_PASSWORD", "")
    sub_key = os.environ.get("ERCOT_PUBLIC_API_SUBSCRIPTION_KEY", "")

    if not all([username, password, sub_key]):
        raise RuntimeError(
            "Missing ERCOT credentials. Set ERCOT_API_USERNAME, ERCOT_API_PASSWORD, "
            "ERCOT_PUBLIC_API_SUBSCRIPTION_KEY in .env or environment."
        )

    # Get auth token for direct API calls (sced_mcpc)
    import requests
    token_url = (
        "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
        "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
    )
    token_resp = requests.post(
        token_url,
        data={
            "username": username,
            "password": password,
            "grant_type": "password",
            "scope": "openid fec253ea-0d06-4272-a5e6-b478baeecd70 offline_access",
            "client_id": "fec253ea-0d06-4272-a5e6-b478baeecd70",
            "response_type": "token",
        },
        timeout=30,
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    token = token_data.get("access_token") or token_data.get("id_token")
    if not token:
        raise RuntimeError(f"No token in auth response: {list(token_data.keys())}")
    logger.info("ERCOT auth token acquired")

    api = _get_api()

    results: dict[str, dict[str, bool]] = {}
    products = ["rt_lmp", "sced_mcpc", "dam_spp", "dam_as", "wind", "solar", "load_actual"]

    current = start
    while current < end_excl:
        logger.info("--- %s ---", current)
        for product in products:
            ok = _fetch_one_day(
                product, current, api=api, token=token, sub_key=sub_key, force=force
            )
            if product not in results:
                results[product] = {}
            results[product][str(current)] = ok
            time.sleep(1.0)  # gentle pacing between products
        current += timedelta(days=1)
        time.sleep(2.0)

    return results


# ── Assembly layer ────────────────────────────────────────────────────────────

def _make_5min_idx(month_start: pd.Timestamp, month_end_excl: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start=month_start, end=month_end_excl - pd.Timedelta(minutes=5), freq="5min")


def _make_hourly_idx(month_start: pd.Timestamp, month_end_excl: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start=month_start, end=month_end_excl - pd.Timedelta(hours=1), freq="h")


def assemble_month(mk: str) -> dict:
    """Assemble one month (YYYY-MM) into forecaster dataset parquets.

    Returns a quality-report dict.
    """
    year, month = int(mk[:4]), int(mk[5:7])
    month_start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    if month == 12:
        month_end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    else:
        month_end = pd.Timestamp(year=year, month=month + 1, day=1, tz="UTC")

    five_min_idx = _make_5min_idx(month_start, month_end)
    hourly_idx = _make_hourly_idx(month_start, month_end)

    report: dict = {"month": mk, "rt": {}, "dam": {}, "sys": {}}

    # ── 1. Try hybridbid processed (primary source for pre-Apr-16 data) ───────
    hb_proc = HYBRIDBID_DIR / "data" / "processed"
    ep_path = hb_proc / "energy_prices" / f"{mk}.parquet"
    as_path = hb_proc / "as_prices" / f"{mk}.parquet"
    sys_path = hb_proc / "system_conditions" / f"{mk}.parquet"

    ep_df = _load_parquet_tz(ep_path) if ep_path.exists() else pd.DataFrame()
    as_df = _load_parquet_tz(as_path) if as_path.exists() else pd.DataFrame()
    sys_df = _load_parquet_tz(sys_path) if sys_path.exists() else pd.DataFrame()

    # ── 2. Supplement with raw fetched data for dates missing from hybridbid ──
    raw_dir = HYBRIDBID_DIR / "data" / "raw"

    # RT LMP from raw
    rt_lmp_extra = _load_raw_rt_lmp(raw_dir / "rt_lmp", month_start, month_end)
    # SCED MCPC from raw
    sced_extra = _load_raw_sced_mcpc(raw_dir / "sced_mcpc", month_start, month_end)
    # DAM SPP from raw daily files
    dam_spp_extra = _load_raw_dam_spp(raw_dir / "dam_spp", month_start, month_end)
    # DAM AS from raw
    dam_as_extra = _load_raw_dam_as(raw_dir / "dam_as", month_start, month_end)
    # System conditions from raw
    wind_extra = _load_raw_wind(raw_dir / "wind", month_start, month_end)
    solar_extra = _load_raw_solar(raw_dir / "solar", month_start, month_end)
    load_extra = _load_raw_load(raw_dir / "load_actual", month_start, month_end)

    # ── 3. Assemble RT prices on 5-min grid ───────────────────────────────────
    rt_out = pd.DataFrame(index=five_min_idx)
    rt_out.index.name = "timestamp_utc"

    # LMP: prefer hybridbid processed, supplement with raw
    lmp_series = _coalesce_5min(
        primary=ep_df.get("rt_lmp") if not ep_df.empty else None,
        secondary=rt_lmp_extra,
        idx=five_min_idx,
    )
    rt_out["lmp"] = lmp_series

    # AS MCPCs: prefer hybridbid processed, supplement with sced_extra
    for hb_col, canon_col in _AS_RT_COLS.items():
        primary = as_df.get(hb_col) if not as_df.empty else None
        secondary = sced_extra.get(canon_col) if sced_extra is not None else None
        rt_out[canon_col] = _coalesce_5min(primary, secondary, five_min_idx)

    # ── 4. Assemble DAM prices on hourly grid ─────────────────────────────────
    dam_out = pd.DataFrame(index=hourly_idx)
    dam_out.index.name = "timestamp_utc"

    # DAM SPP: prefer hybridbid processed, supplement with raw daily files
    primary_spp = None
    if not ep_df.empty and "dam_spp" in ep_df.columns:
        primary_spp = ep_df["dam_spp"].resample("h").first()
    dam_out["dam_spp"] = _coalesce_hourly(primary_spp, dam_spp_extra, hourly_idx)

    # DAM AS MCPCs: hybridbid processed → supplement with dam_as_extra
    for hb_col, canon_col in _AS_DAM_COLS.items():
        primary = None
        if not as_df.empty and hb_col in as_df.columns:
            primary = as_df[hb_col].resample("h").first()
        secondary = dam_as_extra.get(canon_col) if dam_as_extra is not None else None
        dam_out[canon_col] = _coalesce_hourly(primary, secondary, hourly_idx)

    # ── 5. Assemble system conditions on 5-min grid ───────────────────────────
    sys_out = pd.DataFrame(index=five_min_idx)
    sys_out.index.name = "timestamp_utc"

    for col in ["total_load_mw", "wind_actual_mw", "solar_actual_mw", "net_load_mw"]:
        primary = sys_df.get(col) if not sys_df.empty else None
        # Supplement from raw wind/solar/load
        secondary = None
        if col == "wind_actual_mw" and wind_extra is not None:
            secondary = wind_extra
        elif col == "solar_actual_mw" and solar_extra is not None:
            secondary = solar_extra
        elif col == "total_load_mw" and load_extra is not None:
            secondary = load_extra
        sys_out[col] = _coalesce_5min(primary, secondary, five_min_idx)

    # Recompute net_load from components where directly available
    if sys_out["total_load_mw"].notna().any():
        computed_net = (
            sys_out["total_load_mw"]
            - sys_out["wind_actual_mw"].fillna(0)
            - sys_out["solar_actual_mw"].fillna(0)
        )
        # Use computed only where sys_out net_load is missing
        missing_net = sys_out["net_load_mw"].isna()
        sys_out.loc[missing_net, "net_load_mw"] = computed_net[missing_net]

    # ── 6. Write parquets ─────────────────────────────────────────────────────
    for subdir, df in [
        ("rt_prices", rt_out),
        ("dam_prices", dam_out),
        ("system_conditions", sys_out),
    ]:
        out_path = FC_DIR / subdir
        out_path.mkdir(parents=True, exist_ok=True)
        df.reset_index().to_parquet(out_path / f"{mk}.parquet", index=False, compression="snappy")
        logger.info("Wrote %s/%s.parquet (%d rows)", subdir, mk, len(df))

    # ── 7. Build quality report ───────────────────────────────────────────────
    n_intervals = len(five_min_idx)
    for col in RT_PRICE_COLS:
        nan_pct = float(rt_out[col].isna().mean()) * 100
        report["rt"][col] = {
            "total_intervals": n_intervals,
            "nan_count": int(rt_out[col].isna().sum()),
            "nan_pct": round(nan_pct, 2),
        }
    n_hours = len(hourly_idx)
    for col in DAM_PRICE_COLS:
        nan_pct = float(dam_out[col].isna().mean()) * 100
        report["dam"][col] = {
            "total_hours": n_hours,
            "nan_count": int(dam_out[col].isna().sum()),
            "nan_pct": round(nan_pct, 2),
        }
    for col in _SYS_COLS:
        nan_pct = float(sys_out[col].isna().mean()) * 100
        report["sys"][col] = {
            "total_intervals": n_intervals,
            "nan_count": int(sys_out[col].isna().sum()),
            "nan_pct": round(nan_pct, 2),
        }

    return report


# ── Raw data loaders ──────────────────────────────────────────────────────────

def _load_parquet_tz(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def _load_raw_rt_lmp(raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series | None:
    """Load RT LMP from raw daily files → 5-min UTC Series (last SCED per interval)."""
    frames = []
    for f in sorted(raw_dir.glob("*.parquet")):
        try:
            fdate = pd.Timestamp(f.stem, tz="UTC")
        except Exception:
            continue
        if fdate >= start - pd.Timedelta(days=1) and fdate < end:
            frames.append(pd.read_parquet(f))

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    if "Location" in raw.columns:
        raw = raw[raw["Location"] == "HB_HUBAVG"]

    # Normalize timestamp column
    ts_col = next((c for c in raw.columns if "interval" in c.lower() and "start" in c.lower()), None)
    lmp_col = next((c for c in raw.columns if "lmp" in c.lower()), None)
    if ts_col is None or lmp_col is None:
        return None

    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True)
    raw["ts"] = raw["ts"].dt.tz_convert("UTC").dt.floor("5min")
    raw["lmp"] = pd.to_numeric(raw[lmp_col], errors="coerce")

    # Keep last SCED run per 5-min bucket
    raw = raw.sort_values("ts").groupby("ts")["lmp"].last()
    raw = raw[(raw.index >= start) & (raw.index < end)]
    return raw


def _load_raw_sced_mcpc(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame | None:
    """Load SCED MCPC from raw daily files → pivoted wide 5-min DataFrame."""
    frames = []
    for f in sorted(raw_dir.glob("*.parquet")):
        try:
            fdate = pd.Timestamp(f.stem, tz="UTC")
        except Exception:
            continue
        if fdate >= start - pd.Timedelta(days=1) and fdate < end:
            frames.append(pd.read_parquet(f))

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)

    # Normalize
    col_map = {
        "SCEDTimestamp": "sced_timestamp",
        "ASType": "as_type",
        "MCPC": "mcpc",
    }
    raw = raw.rename(columns={k: v for k, v in col_map.items() if k in raw.columns})

    ts = pd.to_datetime(raw["sced_timestamp"], utc=True)
    raw["ts"] = ts.dt.round("5min")
    raw["as_type"] = raw["as_type"].str.upper().str.strip()
    raw["mcpc"] = pd.to_numeric(raw["mcpc"], errors="coerce")

    # Product name normalization
    product_map = {
        "NSRS": "mcpc_nspin", "NSPIN": "mcpc_nspin",
        "REGUP": "mcpc_regup", "REGDN": "mcpc_regdn",
        "RRS": "mcpc_rrs", "ECRS": "mcpc_ecrs",
    }
    raw["canon"] = raw["as_type"].map(product_map)
    raw = raw.dropna(subset=["canon"])

    raw = raw[(raw["ts"] >= start) & (raw["ts"] < end)]

    pivoted = (
        raw.sort_values("ts")
        .groupby(["ts", "canon"])["mcpc"]
        .last()
        .unstack("canon")
    )
    return pivoted


def _load_raw_dam_spp(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series | None:
    """Load DAM SPP (HB_HUBAVG) from raw daily files → hourly UTC Series."""
    frames = []
    for f in sorted(raw_dir.glob("*.parquet")):
        try:
            fdate = pd.Timestamp(f.stem, tz="UTC")
        except Exception:
            continue
        if fdate >= start and fdate < end:
            frames.append(pd.read_parquet(f))

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    if "Location" in raw.columns and "HB_HUBAVG" in raw["Location"].values:
        raw = raw[raw["Location"] == "HB_HUBAVG"].copy()

    ts_col = next(
        (c for c in raw.columns if "interval" in c.lower() and "start" in c.lower()), None
    )
    spp_col = next((c for c in raw.columns if c.upper() == "SPP"), None)
    if ts_col is None or spp_col is None:
        return None

    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.floor("h")
    raw["spp"] = pd.to_numeric(raw[spp_col], errors="coerce")
    raw = raw[(raw["ts"] >= start) & (raw["ts"] < end)]
    series = raw.drop_duplicates(subset=["ts"], keep="last").set_index("ts")["spp"]
    return series


def _load_raw_dam_as(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame | None:
    """Load DAM AS prices from raw daily files → hourly UTC DataFrame."""
    frames = []
    for f in sorted(raw_dir.glob("*.parquet")):
        try:
            fdate = pd.Timestamp(f.stem, tz="UTC")
        except Exception:
            continue
        if fdate >= start and fdate < end:
            frames.append(pd.read_parquet(f))

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    ts_col = next(
        (c for c in raw.columns if "interval" in c.lower() and "start" in c.lower()), None
    )
    if ts_col is None:
        return None

    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.floor("h")
    raw = raw[(raw["ts"] >= start) & (raw["ts"] < end)]

    col_rename = {
        "Non-Spinning Reserves": "dam_mcpc_nspin",
        "Regulation Down": "dam_mcpc_regdn",
        "Regulation Up": "dam_mcpc_regup",
        "Responsive Reserves": "dam_mcpc_rrs",
        "ERCOT Contingency Reserve Service": "dam_mcpc_ecrs",
    }
    raw = raw.rename(columns=col_rename)
    canon_cols = [c for c in col_rename.values() if c in raw.columns]
    if not canon_cols:
        return None

    result = (
        raw[["ts"] + canon_cols]
        .drop_duplicates(subset=["ts"], keep="last")
        .set_index("ts")
    )
    return result


def _load_raw_wind(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series | None:
    """Load wind actual generation → 5-min resampled UTC Series."""
    # Check nested wind/wind directory first, then raw_dir directly
    for wind_dir in [raw_dir / "wind", raw_dir]:
        frames = []
        for f in sorted(wind_dir.glob("*.parquet")):
            try:
                fdate = pd.Timestamp(f.stem, tz="UTC")
            except Exception:
                continue
            if fdate >= start - pd.Timedelta(days=1) and fdate < end:
                frames.append(pd.read_parquet(f))
        if frames:
            break

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    ts_col = next(
        (c for c in raw.columns if "interval" in c.lower() and "start" in c.lower()), None
    )
    gen_col = next((c for c in raw.columns if "gen system wide" in c.lower()), None)
    if ts_col is None or gen_col is None:
        return None

    # Deduplicate by latest publish time
    if "Publish Time" in raw.columns:
        raw = (
            raw.sort_values("Publish Time")
            .groupby(ts_col)
            .last()
            .reset_index()
        )

    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.floor("5min")
    raw["wind"] = pd.to_numeric(raw[gen_col], errors="coerce")
    series = raw.set_index("ts")["wind"]
    # Source is hourly; resample to 5-min and forward-fill within each hour
    series = series.resample("5min").last().ffill(limit=11)
    return series[(series.index >= start) & (series.index < end)]


def _load_raw_solar(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series | None:
    """Load solar actual generation → 5-min resampled UTC Series."""
    for solar_dir in [raw_dir / "solar", raw_dir]:
        frames = []
        for f in sorted(solar_dir.glob("*.parquet")):
            try:
                fdate = pd.Timestamp(f.stem, tz="UTC")
            except Exception:
                continue
            if fdate >= start - pd.Timedelta(days=1) and fdate < end:
                frames.append(pd.read_parquet(f))
        if frames:
            break

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    ts_col = next(
        (c for c in raw.columns if "interval" in c.lower() and "start" in c.lower()), None
    )
    # Solar actual: look for GEN SYSTEM WIDE or similar
    gen_col = next(
        (c for c in raw.columns if "gen" in c.lower() and "system" in c.lower()), None
    )
    if ts_col is None or gen_col is None:
        return None

    if "Publish Time" in raw.columns:
        raw = (
            raw.sort_values("Publish Time")
            .groupby(ts_col)
            .last()
            .reset_index()
        )

    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.floor("5min")
    raw["solar"] = pd.to_numeric(raw[gen_col], errors="coerce")
    series = raw.set_index("ts")["solar"]
    series = series.resample("5min").last().ffill(limit=11)
    return series[(series.index >= start) & (series.index < end)]


def _extract_load_series_from_frame(df: pd.DataFrame) -> pd.Series | None:
    """Extract a UTC-indexed load series from a single parquet frame.

    Handles two formats:
    - Post-settlement (annual): has 'ERCOT' column, rows are one per hour
    - Forecast-by-model (daily): has 'System Total' column and 'In Use Flag'
    """
    ts_col = next(
        (c for c in df.columns if "interval" in c.lower() and "start" in c.lower()), None
    )
    if ts_col is None:
        return None

    # Post-settlement format has 'ERCOT' column
    load_col = next((c for c in df.columns if c.upper() == "ERCOT"), None)
    if load_col is None:
        # Forecast-by-model format has 'System Total'
        load_col = next((c for c in df.columns if "system total" in c.lower()), None)
        if load_col is not None and "In Use Flag" in df.columns:
            active = df[df["In Use Flag"] == True]
            if not active.empty:
                df = active

    if load_col is None:
        return None

    df = df.copy()
    pub_col = next((c for c in df.columns if "publish" in c.lower()), None)
    if pub_col:
        df = df.sort_values(pub_col)

    df["ts"] = pd.to_datetime(df[ts_col], utc=True).dt.floor("5min")
    df["load"] = pd.to_numeric(df[load_col], errors="coerce")
    return df.groupby("ts")["load"].last()


def _load_raw_load(
    raw_dir: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series | None:
    """Load total load → 5-min UTC Series.

    Supports two file formats (processed separately to avoid column conflicts):
    - Annual cumulative ({year}.parquet): post-settlement with 'ERCOT' column
    - Daily ({date}.parquet): get_load_forecast_by_model with 'System Total'
    """
    all_series: list[pd.Series] = []

    # Annual cumulative files (post-settlement, lagged ~60 days)
    for year in range(start.year, end.year + 1):
        f = raw_dir / f"{year}.parquet"
        if f.exists():
            s = _extract_load_series_from_frame(pd.read_parquet(f))
            if s is not None:
                all_series.append(s)

    # Daily files (either format — processed individually to avoid column conflicts)
    for f in sorted(raw_dir.glob("2*.parquet")):
        if "-" not in f.stem:
            continue  # skip annual files (no dash in stem)
        try:
            fdate = pd.Timestamp(f.stem, tz="UTC")
        except Exception:
            continue
        if fdate >= start - pd.Timedelta(days=1) and fdate < end:
            s = _extract_load_series_from_frame(pd.read_parquet(f))
            if s is not None:
                all_series.append(s)

    if not all_series:
        return None

    combined = pd.concat(all_series)
    combined = combined.groupby(level=0).last()  # keep latest value per timestamp
    combined = combined.resample("5min").last().ffill(limit=11)  # ffill within 1h
    return combined[(combined.index >= start) & (combined.index < end)]


# ── Coalesce helpers ──────────────────────────────────────────────────────────

def _coalesce_5min(
    primary: pd.Series | None,
    secondary: pd.Series | None,
    idx: pd.DatetimeIndex,
) -> pd.Series:
    """Combine primary and secondary onto idx; primary wins where non-NaN."""
    result = pd.Series(np.nan, index=idx, dtype=float)

    if secondary is not None and not secondary.empty:
        secondary = secondary.reindex(idx)
        result = result.fillna(secondary)

    if primary is not None and not primary.empty:
        primary_r = primary.reindex(idx)
        result = primary_r.where(primary_r.notna(), result)

    return result


def _coalesce_hourly(
    primary: pd.Series | None,
    secondary: pd.Series | None,
    idx: pd.DatetimeIndex,
) -> pd.Series:
    """Same as _coalesce_5min but for hourly index."""
    return _coalesce_5min(primary, secondary, idx)


# ── Quality gate ──────────────────────────────────────────────────────────────

def run_quality_gate(reports: list[dict], fetch_end: date | None = None) -> tuple[bool, list[str]]:
    """Check assembled data for anomalies. Returns (passed, issues_list).

    Only gates months that are expected to be fully covered:
    - Skips partial months (< 85% of the month lies within the fetch range)
    - For March MCPCs, allows up to 5% NaN (structural gap in hybridbid source
      for the pre-SCED-MCPC-API period at the start of each month)
    """
    issues: list[str] = []
    WARN_RT = 2.0          # % NaN allowed for RT LMP / energy
    WARN_MCPC = 5.0        # % NaN allowed for AS MCPCs (hybridbid coverage gap)
    WARN_DAM = 5.0         # % NaN allowed for DAM (hourly, fewer observations)
    WARN_SYS = 2.0         # % NaN allowed for system conditions

    today = date.today()

    for rpt in reports:
        mk = rpt["month"]
        year, month = int(mk[:4]), int(mk[5:7])
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)
        month_days = (month_end - month_start).days

        # Determine how many days of this month we expect to have data for
        effective_end = min(fetch_end or today, month_end)
        covered_days = max(0, (effective_end - month_start).days)
        coverage_frac = covered_days / month_days

        if coverage_frac < 0.85:
            # Partial month — skip the gate, just log
            logger.info(
                "[%s] Partial month (%.0f%% covered, %d/%d days) — skipping gate",
                mk, coverage_frac * 100, covered_days, month_days,
            )
            continue

        for col, stats in rpt.get("rt", {}).items():
            pct = stats["nan_pct"]
            threshold = WARN_MCPC if col.startswith("mcpc_") else WARN_RT
            if pct > threshold:
                issues.append(
                    f"[{mk}] RT {col}: {pct:.1f}% NaN (threshold {threshold}%)"
                )

        for col, stats in rpt.get("dam", {}).items():
            pct = stats["nan_pct"]
            if pct > WARN_DAM:
                issues.append(f"[{mk}] DAM {col}: {pct:.1f}% NaN (threshold {WARN_DAM}%)")

        for col, stats in rpt.get("sys", {}).items():
            pct = stats["nan_pct"]
            if pct > WARN_SYS:
                issues.append(f"[{mk}] SYS {col}: {pct:.1f}% NaN (threshold {WARN_SYS}%)")

    return len(issues) == 0, issues


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="W3-B data backfill and forecaster assembly")
    parser.add_argument("--start", default="2026-04-16", help="Fetch start date (inclusive)")
    parser.add_argument("--end", default="2026-05-11", help="Fetch end date (exclusive)")
    parser.add_argument(
        "--assemble-only", action="store_true",
        help="Skip API fetch; just assemble from existing raw data"
    )
    parser.add_argument("--force", action="store_true", help="Re-fetch existing cache files")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    fetch_start = date.fromisoformat(args.start)
    fetch_end = date.fromisoformat(args.end)

    logger.info("W3-B data backfill")
    logger.info("  Fetch period: %s to %s (exclusive)", fetch_start, fetch_end)
    logger.info("  Forecaster dir: %s", FC_DIR)
    logger.info("  HybridBid dir: %s", HYBRIDBID_DIR)

    if args.dry_run:
        logger.info("[dry-run] Would fetch %d days, then assemble Jan 9 – May 10",
                    (fetch_end - fetch_start).days)
        return 0

    # ── Step 1: Fetch missing data ────────────────────────────────────────────
    if not args.assemble_only:
        logger.info("Step 1: Fetching %s → %s...", fetch_start, fetch_end)
        fetch_results = run_fetch(fetch_start, fetch_end, force=args.force)

        # Print fetch summary
        for product, days in fetch_results.items():
            n_ok = sum(v for v in days.values())
            n_fail = len(days) - n_ok
            if n_fail > 0:
                logger.warning("%s: %d/%d days failed", product, n_fail, len(days))
                for d, ok in days.items():
                    if not ok:
                        logger.warning("  FAILED: %s/%s", product, d)
            else:
                logger.info("%s: %d/%d days OK", product, n_ok, len(days))
    else:
        logger.info("Step 1: Skipped (--assemble-only)")

    # ── Step 2: Assemble forecaster dataset ───────────────────────────────────
    logger.info("Step 2: Assembling forecaster dataset from Jan 2026 onward...")

    # Determine which months to assemble (Jan 9 through May 10)
    months_to_assemble = [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"
    ]

    reports: list[dict] = []
    for mk in months_to_assemble:
        logger.info("Assembling %s...", mk)
        try:
            rpt = assemble_month(mk)
            reports.append(rpt)
        except Exception as e:
            logger.error("Failed to assemble %s: %s", mk, e)
            import traceback
            traceback.print_exc()

    # ── Step 3: Data quality gate ─────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("DATA QUALITY REPORT")
    logger.info("=" * 60)

    for rpt in reports:
        logger.info("\n--- %s ---", rpt["month"])
        for table, cols in [("rt", rpt.get("rt", {})), ("dam", rpt.get("dam", {})), ("sys", rpt.get("sys", {}))]:
            for col, stats in cols.items():
                key = "total_intervals" if "total_intervals" in stats else "total_hours"
                logger.info(
                    "  %-8s %-24s NaN: %5d/%5d (%.1f%%)",
                    table, col, stats["nan_count"], stats.get(key, 0), stats["nan_pct"]
                )

    passed, issues = run_quality_gate(reports, fetch_end=fetch_end)

    logger.info("")
    if issues:
        logger.error("GATE RESULT: FAILED — %d anomalies detected:", len(issues))
        for issue in issues:
            logger.error("  !! %s", issue)
        logger.error("")
        logger.error("HALT: Report anomalies to chat before proceeding to Task 1.")
        logger.error("Do NOT tune or suppress these issues — they are real findings.")
        return 1
    else:
        logger.info("GATE RESULT: PASSED — all series within quality thresholds.")
        logger.info("Forecaster dataset ready at: %s", FC_DIR)

    # Write report JSON
    report_path = REPO_ROOT / "data" / "audit" / "w3b_backfill_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"reports": reports, "gate_passed": passed}, indent=2))
    logger.info("Report written to %s", report_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
