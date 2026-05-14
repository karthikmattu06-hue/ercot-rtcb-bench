"""ASDC (Ancillary Service Demand Curve) parameter handling.

ASDCs define ERCOT's willingness to procure ancillary services at each price
tier. Under RTC+B, these curves feed directly into the real-time SCED
co-optimization objective, creating price coupling between AS products.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ASDCCurve:
    """Piecewise-linear ASDC for one AS product at one time interval."""

    quantities_mw: np.ndarray  # ascending quantity breakpoints
    prices_per_mw: np.ndarray  # corresponding maximum prices ERCOT will pay

    def __post_init__(self) -> None:
        if len(self.quantities_mw) != len(self.prices_per_mw):
            raise ValueError("quantities and prices must have the same length")
        if not np.all(np.diff(self.quantities_mw) > 0):
            raise ValueError("quantities_mw must be strictly increasing")

    def shadow_price_at(self, cleared_mw: float) -> float:
        """Interpolate the ASDC shadow price at a given cleared quantity."""
        return float(np.interp(cleared_mw, self.quantities_mw, self.prices_per_mw))

    def max_procurement_mw(self) -> float:
        return float(self.quantities_mw[-1])
