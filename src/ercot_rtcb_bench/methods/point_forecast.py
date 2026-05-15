"""Point-forecast BESS baseline (Task 4).

Uses DAM prices as a point forecast for RT clearing prices, optimizes
dispatch over the forecast window, then settles at actual RT prices.
Represents a realistic causal strategy with day-ahead information only.

The optimizer sees dam_prices; revenue is computed at rt_prices.
The DAM Non-Spin split (online/offline) is collapsed to a single nspin
column via PRODUCT_FAMILY before passing to the LP.
"""

from __future__ import annotations

import logging

import pandas as pd

from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.perfect_foresight import (
    _PRICE_COLS,
    PerfectForesightResult,
    perfect_foresight,
)

logger = logging.getLogger(__name__)

_DAM_PRODUCT_MAP = {
    "dam_spp": "lmp",
    "mcpc_regup": "mcpc_regup",
    "mcpc_regdn": "mcpc_regdn",
    "mcpc_rrs": "mcpc_rrs",
    "mcpc_ecrs": "mcpc_ecrs",
    # Non-Spin: max(online, offline) for BESS (conservative; offline is typically excluded)
    "mcpc_nspin_online": "_nspin_online",
    "mcpc_nspin_offline": "_nspin_offline",
}


def _dam_to_forecast_prices(dam_hourly: pd.DataFrame, rt_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Expand DAM hourly prices to 5-minute RT grid by forward-fill.

    The Non-Spin column for BESS uses mcpc_nspin_online (offline is opt-in
    per ADR 0004 config.bidder.dam_offline_nspin = false default).

    Returns DataFrame with columns matching _PRICE_COLS, indexed by rt_index.
    """
    df = dam_hourly.copy()

    # Collapse Non-Spin: use online price (conservative BESS default)
    if "mcpc_nspin_online" in df.columns:
        df["mcpc_nspin"] = df["mcpc_nspin_online"]
    elif "mcpc_nspin_offline" in df.columns:
        df["mcpc_nspin"] = df["mcpc_nspin_offline"]
    else:
        df["mcpc_nspin"] = 0.0

    # Rename DAM SPP → lmp
    if "dam_spp" in df.columns:
        df = df.rename(columns={"dam_spp": "lmp"})

    # Keep only columns we need, reindex to RT 5-min grid
    missing = [c for c in _PRICE_COLS if c not in df.columns]
    if missing:
        logger.warning("DAM prices missing columns %s; filling with 0", missing)
        for col in missing:
            df[col] = 0.0

    df = df[_PRICE_COLS]
    df_rt = df.reindex(rt_index, method="ffill")
    # Any remaining NaN (before first DAM timestamp) → backfill then 0
    df_rt = df_rt.ffill().bfill().fillna(0.0)
    return df_rt


def _settle_at_rt(
    dispatch: pd.DataFrame,
    rt_prices: pd.DataFrame,
) -> pd.DataFrame:
    """Recompute revenue columns using actual RT prices.

    dispatch: output from perfect_foresight (indexed by timestamp_utc)
    rt_prices: RT prices at same 5-min resolution
    """
    dt = 5 / 60  # hours per interval
    rt = rt_prices.reindex(dispatch.index, method="nearest")

    dispatch = dispatch.copy()
    dispatch["lmp"] = rt["lmp"].values
    dispatch["mcpc_regup"] = rt["mcpc_regup"].values
    dispatch["mcpc_regdn"] = rt["mcpc_regdn"].values
    dispatch["mcpc_rrs"] = rt["mcpc_rrs"].values
    dispatch["mcpc_ecrs"] = rt["mcpc_ecrs"].values
    dispatch["mcpc_nspin"] = rt["mcpc_nspin"].values

    net = dispatch["net_energy_mw"].values
    rev_energy = dispatch["lmp"].values * net * dt
    rev_as = (
        dispatch["mcpc_regup"].values * dispatch["award_regup_mw"].values
        + dispatch["mcpc_regdn"].values * dispatch["award_regdn_mw"].values
        + dispatch["mcpc_rrs"].values * dispatch["award_rrs_mw"].values
        + dispatch["mcpc_ecrs"].values * dispatch["award_ecrs_mw"].values
        + dispatch["mcpc_nspin"].values * dispatch["award_nspin_mw"].values
    ) * dt

    dispatch["revenue_energy_usd"] = rev_energy
    dispatch["revenue_as_usd"] = rev_as
    dispatch["revenue_total_usd"] = rev_energy + rev_as
    return dispatch


def point_forecast(
    params: BESSParams,
    rt_prices: pd.DataFrame,
    dam_prices: pd.DataFrame,
    solver_kwargs: dict | None = None,
) -> PerfectForesightResult:
    """Optimize with DAM price forecast; settle at RT prices.

    Args:
        params: BESS physical parameters.
        rt_prices: DataFrame at 5-min resolution indexed by timestamp_utc,
                   columns [lmp, mcpc_regup, mcpc_regdn, mcpc_rrs, mcpc_ecrs, mcpc_nspin].
                   Used for settlement only (not seen by optimizer).
        dam_prices: DataFrame at hourly resolution indexed by timestamp_utc,
                    columns from DAMPrices schema.
        solver_kwargs: Forwarded to solver.solve().

    Returns:
        PerfectForesightResult settled at RT prices.
    """
    rt_index = rt_prices.dropna(subset=["lmp"]).index
    forecast_prices = _dam_to_forecast_prices(dam_prices, rt_index)

    result = perfect_foresight(params, forecast_prices, solver_kwargs=solver_kwargs)
    settled_dispatch = _settle_at_rt(result.dispatch, rt_prices)

    rev_energy = float(settled_dispatch["revenue_energy_usd"].sum())
    rev_as = float(settled_dispatch["revenue_as_usd"].sum())

    return PerfectForesightResult(
        dispatch=settled_dispatch,
        revenue_total=rev_energy + rev_as,
        revenue_energy=rev_energy,
        revenue_as=rev_as,
        solution=result.solution,
    )
