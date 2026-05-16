"""Task 1 — Analog-day matching engine.

For a target (day, horizon_start), selects the N nearest historical analog days
from the pool [pool_start, target_day − 1].

Matching strategy (ADR 0007):
  - Hard filter: same day-type (weekday / weekend / ERCOT-holiday)
  - Continuous distance: normalized Euclidean over the daily net-load profile
  - Z-normalization: each day's profile is z-normalized before distance so both
    absolute level and shape contribute equally
  - Pool start: 2026-01-09 (post-MIP-tighten regime, per locked decisions)
  - Pool-depth gate: < 10 candidates after hard filter → relax to all day-types

Pool exclusions (hard, never overridden):
  - December 2025 (pre-regime)
  - Jan 1–8, 2026 (pre-MIP-tighten)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset

logger = logging.getLogger(__name__)

# Hard pool start (post-MIP-tighten)
POOL_START = date(2026, 1, 9)

# Pool-depth gate: relax day-type filter if fewer than this many candidates
POOL_DEPTH_MIN = 10

# Default number of analogs to select
DEFAULT_N = 40

# NERC holidays observed by ERCOT in 2026 (within Jan–May window)
_NERC_HOLIDAYS_2026: frozenset[date] = frozenset(
    [
        date(2026, 1, 1),   # New Year's Day
        date(2026, 5, 25),  # Memorial Day
        date(2026, 7, 3),   # Independence Day (observed Fri)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
    ]
)


def _day_type(d: date) -> str:
    """Return 'holiday', 'weekend', or 'weekday'."""
    if d in _NERC_HOLIDAYS_2026:
        return "holiday"
    if d.weekday() >= 5:
        return "weekend"
    return "weekday"


def _z_normalize(profile: np.ndarray) -> np.ndarray:
    """Z-normalize a 1-D array. Returns zeros if std ≈ 0."""
    mu = float(profile.mean())
    sigma = float(profile.std())
    if sigma < 1e-6:
        return np.zeros_like(profile)
    return (profile - mu) / sigma


def _impute_nans(profile: np.ndarray) -> np.ndarray:
    """Return copy with NaN → linear interpolation; edge NaNs filled by nearest valid."""
    out = profile.copy()
    if not np.isnan(out).any():
        return out
    valid = np.isfinite(out)
    if not valid.any():
        return np.zeros_like(out)
    xs = np.arange(len(out))
    out[:] = np.interp(xs, xs[valid], out[valid])
    return out


def match_analogs(
    target_day: date,
    dataset: ForecasterDataset,
    pool_start: date = POOL_START,
    n: int = DEFAULT_N,
) -> tuple[list[date], np.ndarray, dict]:
    """Find the N nearest analog days for *target_day*.

    Parameters
    ----------
    target_day : date
        The day to forecast. Pool is [pool_start, target_day − 1].
    dataset : ForecasterDataset
        Data access layer.
    pool_start : date
        First eligible pool day (never Dec 2025 or Jan 1–8).
    n : int
        Maximum analogs to return.

    Returns
    -------
    analog_days : list[date]
        Matched days sorted ascending by distance (nearest first).
    distances : np.ndarray
        Corresponding Euclidean distances on z-normalized net-load profiles.
    info : dict
        Diagnostics: pool_size, matched_count, day_type_relaxed, target_day_type.
    """
    target_type = _day_type(target_day)

    # Target net-load profile
    target_raw = dataset.get_net_load(target_day)
    target_raw = _impute_nans(target_raw)
    target_profile = _z_normalize(target_raw)

    # Build candidate pool
    pool_end = target_day  # exclusive
    available = dataset.available_days(pool_start, pool_end)

    # Hard exclusions (guard against any edge-case overlap)
    available = [
        d for d in available
        if not (d.year == 2025 and d.month == 12)
        and not (d.year == 2026 and d.month == 1 and d.day < 9)
    ]
    pool_size = len(available)

    # Day-type hard filter
    filtered = [d for d in available if _day_type(d) == target_type]
    day_type_relaxed = False

    if len(filtered) < POOL_DEPTH_MIN:
        logger.warning(
            "Pool-depth gate: %s (type=%s) has only %d same-type days; "
            "relaxing to all day-types (%d days).",
            target_day, target_type, len(filtered), pool_size,
        )
        filtered = available
        day_type_relaxed = True

    if not filtered:
        logger.error("Empty analog pool for %s — no usable data in pool period", target_day)
        return [], np.array([]), {
            "pool_size": pool_size,
            "matched_count": 0,
            "day_type_relaxed": day_type_relaxed,
            "target_day_type": target_type,
        }

    # Compute net-load distances
    distances: list[float] = []
    valid_days: list[date] = []

    for pool_day in filtered:
        pool_raw = dataset.get_net_load(pool_day)
        if np.isnan(pool_raw).all():
            continue
        pool_raw = _impute_nans(pool_raw)
        pool_profile = _z_normalize(pool_raw)
        dist = float(np.linalg.norm(target_profile - pool_profile))
        distances.append(dist)
        valid_days.append(pool_day)

    if not valid_days:
        return [], np.array([]), {
            "pool_size": pool_size,
            "matched_count": 0,
            "day_type_relaxed": day_type_relaxed,
            "target_day_type": target_type,
        }

    dist_arr = np.array(distances, dtype=np.float64)
    order = np.argsort(dist_arr)
    top_n = min(n, len(valid_days))

    analog_days = [valid_days[i] for i in order[:top_n]]
    analog_distances = dist_arr[order[:top_n]]

    info = {
        "pool_size": pool_size,
        "matched_count": len(analog_days),
        "day_type_relaxed": day_type_relaxed,
        "target_day_type": target_type,
        "distance_min": float(analog_distances.min()),
        "distance_max": float(analog_distances.max()),
    }
    return analog_days, analog_distances, info
