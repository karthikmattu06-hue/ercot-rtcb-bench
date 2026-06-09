"""MLP price-residual forecaster for DFL (W3-D).

Architecture: 2-layer MLP with ReLU activations, outputting a 6×288 residual
on top of the DAM price forecast. Zero-initialised output layer ensures the
model starts at the DAM baseline (residual ≈ 0) and can only improve.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from ercot_rtcb_bench.forecaster.scenario_tree import N_SERIES, N_STEPS


class PriceResidualMLP(nn.Module):
    """Parametric price forecaster: features → 6×288 residual on DAM forecast.

    Final forecast = DAM prices (broadcast from hourly) + residual.
    AS price residuals are clipped so AS ≥ 0 before LP input; LMP can be negative.

    Args:
        input_dim:  Feature vector dimension (default 419).
        hidden_dim: Hidden layer width (default 256).
        dropout:    Dropout probability on hidden layers (default 0.1).
    """

    def __init__(
        self,
        input_dim: int = 419,
        hidden_dim: int = 256,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.head = nn.Linear(hidden_dim, N_SERIES * N_STEPS)

        # Zero-init: warm-start at DAM forecast (residual ≈ 0)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Feature tensor, shape (..., input_dim).

        Returns:
            Residual tensor, shape (N_SERIES, N_STEPS) = (6, 288).
        """
        h = self.net(x)
        return self.head(h).reshape(N_SERIES, N_STEPS)
