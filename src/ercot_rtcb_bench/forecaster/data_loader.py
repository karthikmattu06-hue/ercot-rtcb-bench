"""Forecaster data loader — reads processed Parquet files into per-day panels.

Reads from two sources (in priority order):
1. data/processed/forecaster/  — extended dataset built by scripts/backfill_w3b.py
2. ~/hybridbid/data/processed/ — fallback for dates not yet in the extended dataset

Per-day panel columns:
  RT prices     : lmp, mcpc_regup, mcpc_regdn, mcpc_rrs, mcpc_ecrs, mcpc_nspin (5-min)
  DAM prices    : dam_spp, dam_mcpc_regup, dam_mcpc_regdn, dam_mcpc_rrs,
                  dam_mcpc_ecrs, dam_mcpc_nspin (hourly → ffill to 5-min)
  System conds  : total_load_mw, wind_actual_mw, solar_actual_mw, net_load_mw (5-min)

All timestamps in UTC. Each day has 288 rows (5-min aligned, no gaps; NaN for missing).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ercot_rtcb_bench.forecaster.scenario_tree import N_STEPS, RESOLUTION_MIN, SERIES_NAMES

logger = logging.getLogger(__name__)

# ── Column mapping from hybridbid processed → canonical ──────────────────────

_EP_COLS = {"rt_lmp": "lmp", "dam_spp": "dam_spp"}
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
_SYS_COLS = {
    "total_load_mw": "total_load_mw",
    "wind_actual_mw": "wind_actual_mw",
    "solar_actual_mw": "solar_actual_mw",
    "net_load_mw": "net_load_mw",
}

# Canonical RT price columns (same order as SERIES_NAMES)
RT_PRICE_COLS = list(SERIES_NAMES)
# Canonical DAM price columns (parallel to RT, same series order)
DAM_PRICE_COLS = ["dam_spp", "dam_mcpc_regup", "dam_mcpc_regdn", "dam_mcpc_rrs",
                  "dam_mcpc_ecrs", "dam_mcpc_nspin"]
SYS_COLS = ["total_load_mw", "wind_actual_mw", "solar_actual_mw", "net_load_mw"]


def _five_min_index(day: date) -> pd.DatetimeIndex:
    """288-element UTC DatetimeIndex for the operating day (midnight-to-midnight)."""
    start = pd.Timestamp(day, tz="UTC")
    return pd.date_range(start=start, periods=N_STEPS, freq=f"{RESOLUTION_MIN}min")


def _month_key(day: date) -> str:
    return f"{day.year}-{day.month:02d}"


class ForecasterDataset:
    """Load and cache per-day price panels for the forecaster.

    Parameters
    ----------
    forecaster_dir : Path
        data/processed/forecaster/ directory (may be empty; falls back to hybridbid).
    hybridbid_dir : Path | None
        ~/hybridbid/data/processed/ directory for fallback. If None, only
        forecaster_dir is searched.
    """

    def __init__(
        self,
        forecaster_dir: Path | None = None,
        hybridbid_dir: Path | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        self._fc_dir = forecaster_dir or (repo_root / "data" / "processed" / "forecaster")
        self._hb_dir = hybridbid_dir or (Path.home() / "hybridbid" / "data" / "processed")
        self._month_cache: dict[str, dict[str, pd.DataFrame]] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    def get_day(self, day: date) -> pd.DataFrame:
        """Return a 288-row panel for *day* with all price + system columns.

        Index: UTC DatetimeIndex (5-min aligned).
        Columns: RT_PRICE_COLS + DAM_PRICE_COLS + SYS_COLS.
        Missing values are NaN (never silently forward-filled across days).
        """
        return self._load_day(day)

    def get_rt_array(self, day: date) -> np.ndarray:
        """RT prices for *day*, shape [6, 288]. NaN where data is missing."""
        panel = self.get_day(day)
        return panel[RT_PRICE_COLS].to_numpy(dtype=np.float64).T  # [6, 288]

    def get_dam_array(self, day: date) -> np.ndarray:
        """DAM prices (ffilled to 5-min) for *day*, shape [6, 288]."""
        panel = self.get_day(day)
        return panel[DAM_PRICE_COLS].to_numpy(dtype=np.float64).T  # [6, 288]

    def get_net_load(self, day: date) -> np.ndarray:
        """Net load profile for *day*, shape [288]. NaN where missing."""
        panel = self.get_day(day)
        return panel["net_load_mw"].to_numpy(dtype=np.float64)

    def available_days(self, start: date, end: date) -> list[date]:
        """Return dates in [start, end) that have at least RT price data."""
        days: list[date] = []
        d = start
        while d < end:
            try:
                panel = self.get_day(d)
                # Day is usable if ≥90% of RT LMP values are non-NaN
                if panel["lmp"].notna().mean() >= 0.90:
                    days.append(d)
            except Exception:
                pass
            d += timedelta(days=1)
        return days

    # ── Internal loading ──────────────────────────────────────────────────────

    def _load_day(self, day: date) -> pd.DataFrame:
        idx = _five_min_index(day)
        mk = _month_key(day)

        if mk not in self._month_cache:
            self._month_cache[mk] = self._load_month(mk)

        month_data = self._month_cache[mk]
        rt_df = month_data.get("rt", pd.DataFrame())
        dam_df = month_data.get("dam", pd.DataFrame())
        sys_df = month_data.get("sys", pd.DataFrame())

        day_start = pd.Timestamp(day, tz="UTC")
        day_end = day_start + pd.Timedelta(hours=24)

        panel = pd.DataFrame(index=idx)
        panel.index.name = "timestamp_utc"

        # RT prices (5-min)
        if not rt_df.empty:
            day_rt = rt_df[(rt_df.index >= day_start) & (rt_df.index < day_end)]
            for col in RT_PRICE_COLS:
                if col in day_rt.columns:
                    panel[col] = day_rt[col].reindex(idx)
                else:
                    panel[col] = np.nan
        else:
            for col in RT_PRICE_COLS:
                panel[col] = np.nan

        # DAM prices (hourly ffilled to 5-min)
        if not dam_df.empty:
            day_dam = dam_df[(dam_df.index >= day_start) & (dam_df.index < day_end)]
            hourly_idx = pd.date_range(day_start, periods=24, freq="h")
            for col in DAM_PRICE_COLS:
                if col in day_dam.columns:
                    hourly = day_dam[col].reindex(hourly_idx)
                    panel[col] = hourly.reindex(idx, method="ffill")
                else:
                    panel[col] = np.nan
        else:
            for col in DAM_PRICE_COLS:
                panel[col] = np.nan

        # System conditions (5-min)
        if not sys_df.empty:
            day_sys = sys_df[(sys_df.index >= day_start) & (sys_df.index < day_end)]
            for col in SYS_COLS:
                if col in day_sys.columns:
                    panel[col] = day_sys[col].reindex(idx)
                else:
                    panel[col] = np.nan
        else:
            for col in SYS_COLS:
                panel[col] = np.nan

        return panel

    def _load_month(self, mk: str) -> dict[str, pd.DataFrame]:
        """Load one month from forecaster_dir or hybridbid fallback."""
        # 1. Try forecaster_dir (canonical extended dataset)
        fc_result = self._try_load_forecaster_month(mk)
        if fc_result is not None:
            return fc_result

        # 2. Fallback to hybridbid processed
        return self._load_hybridbid_month(mk)

    def _try_load_forecaster_month(self, mk: str) -> dict[str, pd.DataFrame] | None:
        """Load from data/processed/forecaster/ monthly parquets."""
        rt_path = self._fc_dir / "rt_prices" / f"{mk}.parquet"
        dam_path = self._fc_dir / "dam_prices" / f"{mk}.parquet"
        sys_path = self._fc_dir / "system_conditions" / f"{mk}.parquet"

        if not rt_path.exists():
            return None

        result: dict[str, pd.DataFrame] = {}
        for key, path, col_map in [
            ("rt", rt_path, None),
            ("dam", dam_path, None),
            ("sys", sys_path, None),
        ]:
            if path.exists():
                df = pd.read_parquet(path)
                if "timestamp_utc" in df.columns:
                    df = df.set_index("timestamp_utc")
                df.index = pd.to_datetime(df.index, utc=True)
                result[key] = df
            else:
                result[key] = pd.DataFrame()

        return result

    def _load_hybridbid_month(self, mk: str) -> dict[str, pd.DataFrame]:
        """Load from hybridbid data/processed/ monthly parquets."""
        result: dict[str, pd.DataFrame] = {}

        ep_path = self._hb_dir / "energy_prices" / f"{mk}.parquet"
        as_path = self._hb_dir / "as_prices" / f"{mk}.parquet"
        sys_path = self._hb_dir / "system_conditions" / f"{mk}.parquet"

        # RT + DAM prices from energy_prices + as_prices
        ep_df = pd.DataFrame()
        as_df = pd.DataFrame()

        if ep_path.exists():
            ep_df = pd.read_parquet(ep_path)
            if not isinstance(ep_df.index, pd.DatetimeIndex):
                ep_df.index = pd.to_datetime(ep_df.index, utc=True)
            else:
                ep_df.index = ep_df.index.tz_convert("UTC")

        if as_path.exists():
            as_df = pd.read_parquet(as_path)
            if not isinstance(as_df.index, pd.DatetimeIndex):
                as_df.index = pd.to_datetime(as_df.index, utc=True)
            else:
                as_df.index = as_df.index.tz_convert("UTC")

        # Assemble RT prices
        rt_df = pd.DataFrame()
        if not ep_df.empty or not as_df.empty:
            rt_cols: dict[str, pd.Series] = {}
            if "rt_lmp" in ep_df.columns:
                rt_cols["lmp"] = ep_df["rt_lmp"]
            for src, dst in _AS_RT_COLS.items():
                if not as_df.empty and src in as_df.columns:
                    rt_cols[dst] = as_df[src]
            if rt_cols:
                rt_df = pd.DataFrame(rt_cols)

        # Assemble DAM prices
        dam_df = pd.DataFrame()
        if not ep_df.empty or not as_df.empty:
            dam_cols: dict[str, pd.Series] = {}
            if "dam_spp" in ep_df.columns:
                dam_cols["dam_spp"] = ep_df["dam_spp"]
            for src, dst in _AS_DAM_COLS.items():
                if not as_df.empty and src in as_df.columns:
                    dam_cols[dst] = as_df[src]
            if dam_cols:
                dam_df = pd.DataFrame(dam_cols)
                # Downsample to hourly (DAM is constant within each hour)
                dam_df = dam_df.resample("h").first()

        result["rt"] = rt_df
        result["dam"] = dam_df

        # System conditions
        if sys_path.exists():
            sys_df = pd.read_parquet(sys_path)
            if not isinstance(sys_df.index, pd.DatetimeIndex):
                sys_df.index = pd.to_datetime(sys_df.index, utc=True)
            else:
                sys_df.index = sys_df.index.tz_convert("UTC")
            # Rename to canonical
            sys_df = sys_df.rename(columns=_SYS_COLS)
            result["sys"] = sys_df[[c for c in SYS_COLS if c in sys_df.columns]]
        else:
            result["sys"] = pd.DataFrame()

        return result
