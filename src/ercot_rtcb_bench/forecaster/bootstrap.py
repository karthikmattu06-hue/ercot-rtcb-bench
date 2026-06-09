"""Whole-day vector block bootstrap + scenario generation.

Design decisions (ADR 0007 / W3-B-fix-2 final):
  - Residual = RT_actual_5min(analog) − DAM_broadcast_5min(analog)
  - Scenario  = DAM_forecast_5min(target) + residual(analog) [+ LMP jitter]
  - The entire [6 × 288] residual block is one indivisible unit (no per-series mixing).
  - Energy LMP (series 0): additive Silverman jitter applied to widen predictive
    interval. σ_lmp = 1.06 · σ̂_residual · N^(−1/5). LMP is NOT clipped.
  - AS MCPC series (1–5): NO jitter. Both additive (W3-B-fix) and log-space
    multiplicative (W3-B-fix-2) jitter were tested and produced higher bias than the
    baseline due to clipping and log-space under-dispersion respectively. The pre-fix
    behavior (DAM + residual, clip at 0) is the least-wrong configuration for a
    stochastic LP: lower bias at the cost of under-dispersion. See ADR 0007.
  - DAM hourly prices are broadcast to 5-min by forward-fill within each hour.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.forecaster.scenario_tree import N_SERIES, N_STEPS, SERIES_NAMES

logger = logging.getLogger(__name__)

# AS series indices (all non-LMP products, non-negative by market design)
_AS_SERIES_IDX: list[int] = [1, 2, 3, 4, 5]  # regup, regdn, rrs, ecrs, nspin


def _silverman_lmp_sigma(lmp_residuals: np.ndarray, n: int) -> float:
    """Silverman bandwidth for additive LMP jitter.

    Parameters
    ----------
    lmp_residuals : np.ndarray, shape [N, 288]
        Pool of N LMP residual day-vectors.
    n : int
        Number of used analog days.

    Returns
    -------
    float
        σ_add = 1.06 · σ̂_residual · N^(−1/5).
    """
    sigma_hat = float(lmp_residuals.std())
    sigma = 1.06 * sigma_hat * (n ** -0.2)
    logger.debug("Silverman LMP additive sigma (N=%d): %.4f $/MWh", n, sigma)
    return sigma


def build_raw_scenarios(
    target_day: date,
    analog_days: list[date],
    dataset: ForecasterDataset,
    jitter_rng: np.random.Generator | None = None,
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
    jitter_rng : np.random.Generator | None
        If provided, applies Silverman-bandwidth additive Gaussian jitter to the
        LMP series only (series 0). AS MCPC series receive no jitter — see module
        docstring for why both jitter approaches were rejected for AS.

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

    if np.isnan(dam_target).all():
        logger.error("No DAM prices for target day %s — cannot build scenarios", target_day)
        empty = np.empty((0, N_SERIES, N_STEPS), dtype=np.float64)
        return empty, np.full((N_SERIES, N_STEPS), np.nan), []

    dam_target = _impute_zero(dam_target)

    # ── Phase 1: collect residuals ────────────────────────────────────────────
    raw_residuals: list[np.ndarray] = []
    used_days: list[date] = []

    for analog_day in analog_days:
        rt_analog = dataset.get_rt_array(analog_day)   # [6, 288]
        dam_analog = dataset.get_dam_array(analog_day)  # [6, 288]

        rt_coverage = float(np.isfinite(rt_analog).mean())
        dam_coverage = float(np.isfinite(dam_analog).mean())
        if rt_coverage < 0.90 or dam_coverage < 0.90:
            logger.debug(
                "Skipping analog %s: RT coverage=%.1f%%, DAM coverage=%.1f%%",
                analog_day, rt_coverage * 100, dam_coverage * 100,
            )
            continue

        rt_analog = _impute_series(rt_analog)
        dam_analog = _impute_zero(dam_analog)

        raw_residuals.append(rt_analog - dam_analog)  # [6, 288]
        used_days.append(analog_day)

    if not raw_residuals:
        logger.error("No usable analog days for %s — all had too much missing data", target_day)
        empty = np.empty((0, N_SERIES, N_STEPS), dtype=np.float64)
        return empty, dam_target, []

    residual_stack = np.stack(raw_residuals, axis=0)  # [N, 6, 288]
    n = len(raw_residuals)

    # ── Phase 2: compute LMP jitter bandwidth (AS: no jitter) ────────────────
    lmp_sigma: float | None = None
    if jitter_rng is not None:
        lmp_sigma = _silverman_lmp_sigma(residual_stack[:, 0, :], n)

    # ── Phase 3: build scenarios ──────────────────────────────────────────────
    raw_scenarios: list[np.ndarray] = []

    for residual in raw_residuals:
        scenario = dam_target + residual  # [6, 288]

        if lmp_sigma is not None:
            # LMP only: additive Gaussian jitter; can remain negative (correct)
            scenario[0, :] += jitter_rng.normal(0.0, lmp_sigma, N_STEPS)

        # AS: clip at 0 (residual can push below zero; no jitter applied)
        scenario[_AS_SERIES_IDX, :] = np.maximum(scenario[_AS_SERIES_IDX, :], 0.0)

        raw_scenarios.append(scenario)

    scenarios = np.stack(raw_scenarios, axis=0)  # [N, 6, 288]
    logger.debug(
        "Built %d raw scenarios for %s from %d analogs (lmp_jitter=%s)",
        len(raw_scenarios), target_day, len(analog_days), jitter_rng is not None,
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
