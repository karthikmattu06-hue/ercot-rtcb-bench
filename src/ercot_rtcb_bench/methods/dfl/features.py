"""Feature engineering for the DFL MLP forecaster (W3-D).

Feature vector (FEATURE_DIM=419):
  [0:11]    Calendar: weekday one-hot (7), day-of-year sin/cos (2), month sin/cos (2)
  [11:155]  DAM prices: 6 series × 24 hourly values = 144
  [155:251] System conditions: 4 features × 24 hourly means = 96
  [251:419] Lag realized prices: 7 days × 6 series × 4 stats (mean/std/max/min) = 168
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset

# ── Layout constants ──────────────────────────────────────────────────────────
_N_CALENDAR = 11       # weekday(7) + doy sin/cos(2) + month sin/cos(2)
_N_DAM = 6 * 24        # 144
_N_SYS = 4 * 24        # 96
_N_LAG = 7 * 6 * 4    # 168  (7 days × 6 series × [mean, std, max, min])
FEATURE_DIM: int = _N_CALENDAR + _N_DAM + _N_SYS + _N_LAG  # 419

_SYS_COLS = ["total_load_mw", "wind_actual_mw", "solar_actual_mw", "net_load_mw"]


def calendar_features(day: date) -> np.ndarray:
    """11-element calendar encoding for *day*."""
    # Weekday one-hot (Mon=0 .. Sun=6)
    wday = day.weekday()
    wday_oh = np.zeros(7, dtype=np.float32)
    wday_oh[wday] = 1.0

    # Day-of-year: sin/cos (handles leap years gracefully)
    doy = day.timetuple().tm_yday
    year_len = 366 if (day.year % 4 == 0 and (day.year % 100 != 0 or day.year % 400 == 0)) else 365
    doy_sin = math.sin(2 * math.pi * doy / year_len)
    doy_cos = math.cos(2 * math.pi * doy / year_len)

    # Month sin/cos
    m_sin = math.sin(2 * math.pi * day.month / 12)
    m_cos = math.cos(2 * math.pi * day.month / 12)

    return np.concatenate([wday_oh, [doy_sin, doy_cos, m_sin, m_cos]]).astype(np.float32)


def lag_features(day: date, dataset: ForecasterDataset) -> np.ndarray:
    """168-element lag feature: stats over last 7 days of realized prices."""
    parts: list[np.ndarray] = []
    for lag in range(1, 8):
        lag_day = day - timedelta(days=lag)
        try:
            rt = dataset.get_rt_array(lag_day)  # [6, 288]
            rt = np.nan_to_num(rt, nan=0.0)
            mean = rt.mean(axis=1)    # [6]
            std  = rt.std(axis=1)     # [6]
            mx   = rt.max(axis=1)     # [6]
            mn   = rt.min(axis=1)     # [6]
            parts.append(np.stack([mean, std, mx, mn], axis=1).flatten())  # [24]
        except Exception:
            parts.append(np.zeros(24, dtype=np.float32))
    return np.concatenate(parts).astype(np.float32)  # [168]


def extract_features(day: date, dataset: ForecasterDataset) -> np.ndarray:
    """Extract the full FEATURE_DIM=419 feature vector for *day*.

    All values are raw (un-normalised); apply FeatureNormalizer before MLP input.
    """
    panel = dataset.get_day(day)

    # DAM prices: 6 series × 24 hourly values (first 5-min of each hour)
    dam = dataset.get_dam_array(day)   # [6, 288]
    dam_hourly = dam[:, ::12].flatten().astype(np.float32)  # [144]

    # System conditions: 4 features × 24 hourly means
    sys_mat = np.nan_to_num(
        panel[_SYS_COLS].to_numpy(dtype=np.float32),  # [288, 4]
        nan=0.0,
    )
    sys_hourly = sys_mat.reshape(24, 12, 4).mean(axis=1).T.flatten()  # [96]

    return np.concatenate([
        calendar_features(day),  # [11]
        dam_hourly,              # [144]
        sys_hourly,              # [96]
        lag_features(day, dataset),  # [168]
    ])  # [419]


class FeatureNormalizer:
    """Per-feature z-normalisation fitted on the training set."""

    mean_: np.ndarray
    std_: np.ndarray

    def fit(self, features_list: list[np.ndarray]) -> None:
        mat = np.stack(features_list, axis=0)  # [N, FEATURE_DIM]
        self.mean_ = mat.mean(axis=0).astype(np.float32)
        self.std_  = mat.std(axis=0).astype(np.float32)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean_) / (self.std_ + 1e-8)).astype(np.float32)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, mean=self.mean_, std=self.std_)

    @classmethod
    def load(cls, path: Path) -> FeatureNormalizer:
        data = np.load(Path(path))
        obj = cls()
        obj.mean_ = data["mean"]
        obj.std_  = data["std"]
        return obj
