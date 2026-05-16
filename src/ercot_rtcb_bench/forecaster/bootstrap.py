"""Task 2 — Whole-day vector block bootstrap + scenario generation.

Design decisions (ADR 0007):
  - Residual = RT_actual_5min(analog) − DAM_broadcast_5min(analog)
  - Scenario  = DAM_forecast_5min(target) + residual(analog)
  - The entire [6 × 288] residual block is one indivisible unit (no per-series mixing).
  - Energy LMP (series 0) is NOT clipped — negative prices are valid ERCOT signal.
  - AS MCPC series (1–5) are clipped at 0 (non-negative by market design).
  - DAM hourly prices are broadcast to 5-min by forward-fill within each hour.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.forecaster.scenario_tree import N_SERIES, N_STEPS, SERIES_NAMES

logger = logging.getLogger(__name__)

# Series indices where non-negativity must be enforced (all AS products)
_AS_SERIES_IDX: list[int] = [1, 2, 3, 4, 5]  # regup, regdn, rrs, ecrs, nspin


def build_raw_scenarios(
    target_day: date,
    analog_days: list[date],
    dataset: ForecasterDataset,
) -> tuple[np.ndarray, np.ndarray, list[date]]:
    """Compute [N × 6 × 288] raw scenarios from analog residuals.

    Parameters
    ----------
    target_day : date
        Operating day being forecast.
    analog_days : list[date]
        Matched analog days (from analog.match_analogs), sorted nearest-first.
    dataset : ForecasterDataset
        Data access layer.

    Returns
    -------
    scenarios : np.ndarray, shape [N, 6, 288]
        Raw scenario array. N ≤ len(analog_days) (days with missing data dropped).
    point_forecast : np.ndarray, shape [6, 288]
        Target-day DAM prices broadcast to 5-min.
    used_days : list[date]
        Analog days actually used (subset of analog_days, missing data dropped).
    """
    dam_target = dataset.get_dam_array(target_day)  # [6, 288]

    # Handle fully missing DAM target gracefully
    if np.isnan(dam_target).all():
        logger.error("No DAM prices for target day %s — cannot build scenarios", target_day)
        empty = np.empty((0, N_SERIES, N_STEPS), dtype=np.float64)
        return empty, np.full((N_SERIES, N_STEPS), np.nan), []

    # Impute any remaining NaNs in DAM target with 0 (shouldn't happen in practice)
    dam_target = _impute_zero(dam_target)

    raw_scenarios: list[np.ndarray] = []
    used_days: list[date] = []

    for analog_day in analog_days:
        rt_analog = dataset.get_rt_array(analog_day)   # [6, 288]
        dam_analog = dataset.get_dam_array(analog_day)  # [6, 288]

        # Skip this analog if too much data is missing
        rt_coverage = float(np.isfinite(rt_analog).mean())
        dam_coverage = float(np.isfinite(dam_analog).mean())
        if rt_coverage < 0.90 or dam_coverage < 0.90:
            logger.debug(
                "Skipping analog %s: RT coverage=%.1f%%, DAM coverage=%.1f%%",
                analog_day, rt_coverage * 100, dam_coverage * 100,
            )
            continue

        # Impute remaining NaNs to preserve whole-block integrity
        rt_analog = _impute_series(rt_analog)
        dam_analog = _impute_zero(dam_analog)

        # Residual = RT_actual − DAM_broadcast (for this analog day)
        residual = rt_analog - dam_analog  # [6, 288]

        # Scenario = DAM_target + residual
        scenario = dam_target + residual    # [6, 288]

        # Clip non-negative constraint on AS MCPC series (not LMP)
        scenario[_AS_SERIES_IDX, :] = np.clip(scenario[_AS_SERIES_IDX, :], 0.0, None)

        raw_scenarios.append(scenario)
        used_days.append(analog_day)

    if not raw_scenarios:
        logger.error("No usable analog days for %s — all had too much missing data", target_day)
        empty = np.empty((0, N_SERIES, N_STEPS), dtype=np.float64)
        return empty, dam_target, []

    scenarios = np.stack(raw_scenarios, axis=0)  # [N, 6, 288]
    logger.debug(
        "Built %d raw scenarios for %s from %d analogs",
        len(raw_scenarios), target_day, len(analog_days),
    )
    return scenarios, dam_target, used_days


def _impute_series(arr: np.ndarray) -> np.ndarray:
    """Impute NaNs in a [6, 288] array per-series via linear interpolation."""
    out = arr.copy()
    for i in range(out.shape[0]):
        row = out[i]
        if not np.isnan(row).any():
            continue
        valid = np.isfinite(row)
        if not valid.any():
            out[i] = 0.0
            continue
        xs = np.arange(len(row))
        out[i] = np.interp(xs, xs[valid], row[valid])
    return out


def _impute_zero(arr: np.ndarray) -> np.ndarray:
    """Replace NaNs with 0 in a [N_SERIES, N_STEPS] array."""
    out = arr.copy()
    out[np.isnan(out)] = 0.0
    return out
