"""Bootstrap probabilistic forecaster — orchestration layer.

Combines analog matching, residual bootstrap, and k-medoids reduction into
a single public interface that returns a ScenarioTree.

Usage
-----
    from ercot_rtcb_bench.forecaster import BootstrapForecaster
    fc = BootstrapForecaster()
    tree = fc.forecast(date(2026, 4, 20))
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from ercot_rtcb_bench.forecaster.analog import DEFAULT_N, POOL_START, match_analogs
from ercot_rtcb_bench.forecaster.bootstrap import build_raw_scenarios
from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.forecaster.reduce import DEFAULT_K, reduce_scenarios
from ercot_rtcb_bench.forecaster.scenario_tree import N_STEPS, ScenarioTree

logger = logging.getLogger(__name__)


class BootstrapForecaster:
    """Whole-day vector block bootstrap forecaster for ERCOT 6-series prices.

    Parameters
    ----------
    dataset : ForecasterDataset | None
        Data access layer. If None, constructs a default instance that reads from
        ~/hybridbid/data/processed/ with fallback to data/processed/forecaster/.
    k : int
        Number of representative scenarios after k-medoids reduction (default 15).
    n_analogs : int
        Maximum analog days to consider before reduction (default 40).
    pool_start : date
        First eligible pool day (default 2026-01-09, post-MIP-tighten).
    random_seed : int
        Seed for k-medoids initialization reproducibility.
    """

    def __init__(
        self,
        dataset: ForecasterDataset | None = None,
        k: int = DEFAULT_K,
        n_analogs: int = DEFAULT_N,
        pool_start: date = POOL_START,
        random_seed: int = 42,
    ) -> None:
        self.dataset = dataset or ForecasterDataset()
        self.k = k
        self.n_analogs = n_analogs
        self.pool_start = pool_start
        self.random_seed = random_seed

    def forecast(self, target_day: date) -> ScenarioTree:
        """Generate a ScenarioTree for *target_day*.

        Parameters
        ----------
        target_day : date
            The operating day to forecast. Must be after pool_start + at least
            POOL_DEPTH_MIN days.

        Returns
        -------
        ScenarioTree
            K scenarios [K × 6 × 288] with probability weights, plus the
            DAM point forecast [6 × 288] retained for diagnostics.

        Raises
        ------
        ValueError
            If no scenarios can be generated (no usable analog days).
        """
        logger.info("Forecasting %s (K=%d, N_analogs=%d)", target_day, self.k, self.n_analogs)

        # ── Task 1: analog matching ───────────────────────────────────────────
        analog_days, distances, match_info = match_analogs(
            target_day=target_day,
            dataset=self.dataset,
            pool_start=self.pool_start,
            n=self.n_analogs,
        )

        if not analog_days:
            raise ValueError(
                f"No analog days found for {target_day}. "
                f"Pool size: {match_info.get('pool_size', 0)}"
            )

        # ── Task 2: residual bootstrap ────────────────────────────────────────
        raw_scenarios, point_forecast, used_days = build_raw_scenarios(
            target_day=target_day,
            analog_days=analog_days,
            dataset=self.dataset,
        )

        if raw_scenarios.shape[0] == 0:
            raise ValueError(
                f"No usable analog data for {target_day} — all analogs had missing prices."
            )

        # ── Task 3: k-medoids reduction ───────────────────────────────────────
        scenarios, probabilities = reduce_scenarios(
            raw_scenarios=raw_scenarios,
            k=self.k,
            random_seed=self.random_seed,
        )

        # ── Task 4: assemble ScenarioTree ─────────────────────────────────────
        horizon_start = np.datetime64(
            datetime.combine(target_day, datetime.min.time()).replace(tzinfo=timezone.utc)
        )

        metadata = {
            "target_day": str(target_day),
            "pool_size": match_info["pool_size"],
            "matched_count": match_info["matched_count"],
            "raw_scenario_count": int(raw_scenarios.shape[0]),
            "used_scenario_count": int(scenarios.shape[0]),
            "day_type_relaxed": match_info["day_type_relaxed"],
            "target_day_type": match_info["target_day_type"],
            "generation_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "K": int(scenarios.shape[0]),
            "n_analogs_requested": self.n_analogs,
            "pool_start": str(self.pool_start),
            "analog_days": [str(d) for d in used_days],
            "distance_min": match_info.get("distance_min"),
            "distance_max": match_info.get("distance_max"),
        }

        tree = ScenarioTree(
            horizon_start=horizon_start,
            scenarios=scenarios,
            probabilities=probabilities,
            point_forecast=point_forecast,
            metadata=metadata,
        )

        logger.info(
            "ScenarioTree(%s): K=%d scenarios from %d analogs (pool=%d, relaxed=%s)",
            target_day, tree.n_scenarios, len(used_days),
            match_info["pool_size"], match_info["day_type_relaxed"],
        )
        return tree
