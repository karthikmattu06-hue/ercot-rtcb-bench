"""ScenarioTree — shared contract between W3-B forecaster, W3-C stochastic MILP, and W3-D DFL.

Two-stage fan (not deep tree): one root node, K leaf scenarios, each a full-day
price trajectory for all 6 series at 5-minute resolution.

Series order (fixed, index-stable):
    0: lmp        ($/MWh — energy, can be negative)
    1: mcpc_regup ($/MW — non-negative)
    2: mcpc_regdn ($/MW — non-negative)
    3: mcpc_rrs   ($/MW — non-negative)
    4: mcpc_ecrs  ($/MW — non-negative)
    5: mcpc_nspin ($/MW — non-negative)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

SERIES_NAMES: list[str] = [
    "lmp",
    "mcpc_regup",
    "mcpc_regdn",
    "mcpc_rrs",
    "mcpc_ecrs",
    "mcpc_nspin",
]

N_SERIES = len(SERIES_NAMES)
N_STEPS = 288  # 5-min intervals per day
RESOLUTION_MIN = 5


@dataclass
class ScenarioTree:
    """Two-stage stochastic price fan for one operating day.

    Attributes
    ----------
    horizon_start : np.datetime64
        UTC timestamp of the first 5-min interval (midnight UTC of the operating day).
    scenarios : np.ndarray, shape [K, 6, 288]
        K scenario trajectories, each [6 series × 288 intervals].
    probabilities : np.ndarray, shape [K]
        Scenario weights, sum to 1.0.
    point_forecast : np.ndarray, shape [6, 288]
        DAM prices broadcast to 5-min resolution (retained for diagnostics).
    metadata : dict
        target_day, pool_size, matched_count, generation_timestamp, K, normalization.
    """

    horizon_start: np.datetime64
    scenarios: np.ndarray        # [K, 6, 288]
    probabilities: np.ndarray    # [K]
    point_forecast: np.ndarray   # [6, 288]
    metadata: dict[str, Any] = field(default_factory=dict)

    # read-only derived properties
    resolution_min: int = field(init=False, repr=False)
    n_steps: int = field(init=False, repr=False)
    n_scenarios: int = field(init=False, repr=False)
    series_names: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.resolution_min = RESOLUTION_MIN
        self.n_steps = N_STEPS
        self.n_scenarios = int(self.scenarios.shape[0])
        self.series_names = list(SERIES_NAMES)
        self._validate()

    def _validate(self) -> None:
        assert self.scenarios.shape == (self.n_scenarios, N_SERIES, N_STEPS), (
            f"scenarios must be [{self.n_scenarios}, {N_SERIES}, {N_STEPS}], "
            f"got {self.scenarios.shape}"
        )
        assert self.probabilities.shape == (self.n_scenarios,), (
            f"probabilities must be [{self.n_scenarios}], got {self.probabilities.shape}"
        )
        assert self.point_forecast.shape == (N_SERIES, N_STEPS), (
            f"point_forecast must be [{N_SERIES}, {N_STEPS}], got {self.point_forecast.shape}"
        )
        prob_sum = float(self.probabilities.sum())
        assert abs(prob_sum - 1.0) < 1e-6, f"probabilities must sum to 1.0, got {prob_sum}"

    # ── Consumer interfaces ───────────────────────────────────────────────────

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (scenarios, probabilities, point_forecast) as numpy arrays for Gurobi."""
        return self.scenarios.copy(), self.probabilities.copy(), self.point_forecast.copy()

    def as_tensor(self, framework: str = "torch") -> Any:
        """Return tensors for the DFL differentiable layer (W3-D).

        Returns (scenarios_tensor, probabilities_tensor, point_forecast_tensor).
        Numpy arrays are the source of truth; this is a thin conversion wrapper.
        """
        if framework == "torch":
            import torch  # type: ignore[import]
            return (
                torch.from_numpy(self.scenarios.astype(np.float32)),
                torch.from_numpy(self.probabilities.astype(np.float32)),
                torch.from_numpy(self.point_forecast.astype(np.float32)),
            )
        raise ValueError(f"Unknown framework: {framework!r}. Supported: 'torch'")

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Serialize to .npz (arrays) + .json (metadata)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        meta = dict(self.metadata)
        meta["horizon_start"] = str(self.horizon_start)
        meta["series_names"] = self.series_names

        np.savez_compressed(
            path.with_suffix(".npz"),
            scenarios=self.scenarios,
            probabilities=self.probabilities,
            point_forecast=self.point_forecast,
        )
        (path.with_suffix(".json")).write_text(json.dumps(meta, indent=2, default=str))

    @classmethod
    def load(cls, path: str | Path) -> "ScenarioTree":
        """Deserialize from .npz + .json written by save()."""
        path = Path(path)
        arrays = np.load(path.with_suffix(".npz"))
        meta_text = path.with_suffix(".json").read_text()
        meta = json.loads(meta_text)

        horizon_start = np.datetime64(meta.pop("horizon_start"))
        meta.pop("series_names", None)  # derived from module constant

        return cls(
            horizon_start=horizon_start,
            scenarios=arrays["scenarios"],
            probabilities=arrays["probabilities"],
            point_forecast=arrays["point_forecast"],
            metadata=meta,
        )

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def mean_trajectory(self) -> np.ndarray:
        """Probability-weighted mean scenario, shape [6, 288]."""
        return (self.scenarios * self.probabilities[:, None, None]).sum(axis=0)

    def quantile(self, q: float) -> np.ndarray:
        """Empirical quantile across scenarios (sorted by prob weight), shape [6, 288]."""
        # Sort scenarios and build CDF
        order = np.argsort(self.scenarios, axis=0)
        sorted_s = np.take_along_axis(self.scenarios, order, axis=0)
        sorted_p = self.probabilities[order]
        cdf = np.cumsum(sorted_p, axis=0)
        idx = np.argmax(cdf >= q, axis=0)  # first scenario crossing quantile
        return sorted_s[idx, np.arange(N_SERIES)[:, None], np.arange(N_STEPS)[None, :]]

    def interval_80(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (lo, hi) for the 80% predictive interval, shape [6, 288] each."""
        return self.quantile(0.10), self.quantile(0.90)

    def __repr__(self) -> str:
        return (
            f"ScenarioTree(K={self.n_scenarios}, series={self.series_names}, "
            f"horizon={self.horizon_start}, "
            f"p_sum={self.probabilities.sum():.4f})"
        )
