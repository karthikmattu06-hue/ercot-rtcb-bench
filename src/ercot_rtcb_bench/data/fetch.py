"""ERCOT API client wrapper for fetching post-RTC+B market data.

Wraps gridstatus ErcotAPI/Ercot clients with:
  - Retry logic with exponential backoff (429 and 5xx)
  - Per-product caching to daily Parquet files
  - Rate limit handling (ERCOT API enforces ~10 req/min per endpoint)

Requires environment variables (in .env):
    ERCOT_API_USERNAME
    ERCOT_API_PASSWORD
    ERCOT_PUBLIC_API_SUBSCRIPTION_KEY

Products covered:
    rt_lmp        — RT SCED LMP for a settlement point (NP6-788-CD)
    dam_spp       — DAM Settlement Point Price (hourly)
    dam_as        — DAM AS clearing prices (hourly, all 5 products)
    sced_mcpc     — RT SCED MCPC for all AS products (5-min, post-RTC+B)
    load_actual   — Actual load (hourly)
    load_forecast — Load forecast (hourly)
    wind          — Wind actual + forecast (hourly)
    solar         — Solar actual + forecast (hourly)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

_api_client = None
_scraper_client = None


def _get_api():  # type: ignore[return]
    global _api_client
    if _api_client is not None:
        return _api_client
    try:
        from gridstatus.ercot_api.ercot_api import ErcotAPI
    except ImportError:
        raise ImportError("gridstatus>=0.35.0 required: pip install 'ercot-rtcb-bench[fetch]'") from None
    _api_client = ErcotAPI(sleep_seconds=2.0, max_retries=5)
    _api_client.get_token()
    return _api_client


def _get_scraper():  # type: ignore[return]
    global _scraper_client
    if _scraper_client is not None:
        return _scraper_client
    from gridstatus import Ercot
    _scraper_client = Ercot()
    return _scraper_client


def _with_retry(fn, *args, max_retries: int = 5, base_delay: float = 2.0, **kwargs):
    """Call fn with exponential backoff on 429/5xx errors."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate limit" in msg or "too many" in msg
            is_server_error = any(f"{code}" in msg for code in [500, 502, 503, 504])
            if (is_rate_limit or is_server_error) and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning("Attempt %d failed (%s). Retrying in %.1fs...", attempt + 1, e, delay)
                time.sleep(delay)
            else:
                raise


def _cache_path(raw_dir: Path, product: str, date_str: str) -> Path:
    path = raw_dir / product
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{date_str}.parquet"


def fetch_and_cache(
    product: str,
    start: str,
    end: str,
    raw_dir: Path,
    force: bool = False,
    **kwargs,
) -> dict[str, bool]:
    """Fetch a product for [start, end) date range, caching per-day files.

    Returns a dict mapping date_str → success.
    """
    dates = pd.date_range(start=start, end=end, freq="D", inclusive="left")
    results: dict[str, bool] = {}

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        cache = _cache_path(raw_dir, product, date_str)
        if cache.exists() and not force:
            logger.debug("Cache hit: %s/%s", product, date_str)
            results[date_str] = True
            continue
        try:
            df = _fetch_one_day(product, date, **kwargs)
            if df is not None and not df.empty:
                df.to_parquet(cache, compression="snappy")
                logger.info("Fetched %s/%s (%d rows)", product, date_str, len(df))
                results[date_str] = True
            else:
                logger.warning("Empty result: %s/%s", product, date_str)
                results[date_str] = False
        except Exception as e:
            logger.error("Failed %s/%s: %s", product, date_str, e)
            results[date_str] = False

    return results


def _fetch_one_day(product: str, date: pd.Timestamp, **kwargs) -> pd.DataFrame | None:
    """Dispatch to the appropriate fetch function for a single day."""
    next_day = date + pd.Timedelta(days=1)
    start_str = date.strftime("%Y-%m-%d")
    end_str = next_day.strftime("%Y-%m-%d")

    location = kwargs.get("location", "HB_HUBAVG")

    if product == "rt_lmp":
        api = _get_api()
        return _with_retry(
            api.get_lmp_by_settlement_point,
            start=start_str,
            end=end_str,
            location_name=location,
        )
    if product == "dam_spp":
        scraper = _get_scraper()
        return _with_retry(scraper.get_dam_spp, year=date.year)
    if product == "dam_as":
        api = _get_api()
        return _with_retry(api.get_as_prices, start=start_str, end=end_str)
    if product == "load_actual":
        scraper = _get_scraper()
        return _with_retry(scraper.get_hourly_load_post_settlements, start=start_str, end=end_str)
    if product == "load_forecast":
        api = _get_api()
        return _with_retry(api.get_load_forecast_by_model, start=start_str, end=end_str)
    if product == "wind":
        api = _get_api()
        return _with_retry(api.get_wind_actual_and_forecast_hourly, start=start_str, end=end_str)
    if product == "solar":
        api = _get_api()
        return _with_retry(api.get_solar_actual_and_forecast_hourly, start=start_str, end=end_str)

    raise ValueError(f"Unknown product: {product}")
