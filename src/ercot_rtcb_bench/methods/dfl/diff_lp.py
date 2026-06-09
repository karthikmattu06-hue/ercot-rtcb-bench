"""Differentiable BESS QP layer for DFL training (W3-D) — per-unit formulation.

All CVXPY decision variables are normalised to [0, 1]:
  d_pu  = d  / P        (discharge, per-unit of rated power)
  c_pu  = c  / P        (charge)
  a_*_pu = a_* / P      (AS capacities)
  s_pu  = s  / E        (SoC, per-unit of total energy)

Per-unit SoC dynamics:
  s_pu[t+1] = s_pu[t] - ratio * d_pu[t] + ratio * rte * c_pu[t]
  where ratio = dt * P / E  (≈ 0.021 for 100 MW / 400 MWh, dt=5 min)

All variables in [0, 1] and constraint coefficients O(1) → well-conditioned SCS;
prior physical-unit formulation produced "Solved/Inaccurate" with violations
up to 17.8 MWh because SCS mixed [0,100] MW and [0,400] MWh variables.

BESSQPLayer is the public API: it accepts and returns physical-unit tensors
(MW / MWh / $/MWh) and converts internally. Call signature matches the old
CvxpyLayer so train.py._step needs no changes.
"""

from __future__ import annotations

import cvxpy as cp
import torch
from cvxpylayers.torch import CvxpyLayer

from ercot_rtcb_bench.methods.battery import BESSParams

T_TRAIN = 12   # training horizon = 1h = committed horizon (5-min intervals)
EPS = 0.1      # QP regularizer coefficient (per-unit); 1e-3 gives near-zero gradients


def _build_pu_layer(
    ratio: float,
    rte: float,
    nspin_ratio: float,
    s_min_pu: float,
    T: int,
    eps: float,
) -> CvxpyLayer:
    """Inner per-unit CvxpyLayer.  All variables in [0, 1].

    Parameters received are already scaled:
      lmp_sc = lmp * dt * P   ($/interval at rated power, O($100-$1000))
      term_val = term_lmp * E  ($ per unit SoC at terminal step)
      s0_pu   = s0 / E         (dimensionless, ∈ [0, 1])
    """
    lmp_sc      = cp.Parameter(T, name="lmp_sc")
    mcpc_ru_sc  = cp.Parameter(T, name="mcpc_ru_sc")
    mcpc_rd_sc  = cp.Parameter(T, name="mcpc_rd_sc")
    mcpc_rrs_sc = cp.Parameter(T, name="mcpc_rrs_sc")
    mcpc_ecrs_sc = cp.Parameter(T, name="mcpc_ecrs_sc")
    mcpc_ns_sc  = cp.Parameter(T, name="mcpc_ns_sc")
    s0_pu_p     = cp.Parameter(nonneg=True, name="s0_pu")
    term_val_p  = cp.Parameter(name="term_val")

    d_pu   = cp.Variable(T, nonneg=True, name="d_pu")
    c_pu   = cp.Variable(T, nonneg=True, name="c_pu")
    a_ru   = cp.Variable(T, nonneg=True, name="a_ru")
    a_rd   = cp.Variable(T, nonneg=True, name="a_rd")
    a_rrs  = cp.Variable(T, nonneg=True, name="a_rrs")
    a_ecrs = cp.Variable(T, nonneg=True, name="a_ecrs")
    a_ns   = cp.Variable(T, nonneg=True, name="a_ns")
    s_pu   = cp.Variable(T + 1, name="s_pu")

    constraints = [
        s_pu[0] == s0_pu_p,
        s_pu[1:] == s_pu[:T] - ratio * d_pu + ratio * rte * c_pu,
        s_pu >= s_min_pu,
        s_pu <= 1.0,
        d_pu   <= 1.0,
        c_pu   <= 1.0,
        a_ru   <= 1.0,
        a_rd   <= 1.0,
        a_rrs  <= 1.0,
        a_ecrs <= 1.0,
        a_ns   <= 1.0,
        d_pu + a_ru + a_rrs + a_ecrs + a_ns <= 1.0,
        c_pu + a_rd <= 1.0,
        nspin_ratio * a_ns <= s_pu[:T],
    ]

    net_pu = d_pu - c_pu
    rev_pu = (
        lmp_sc      @ net_pu
        + mcpc_ru_sc  @ a_ru
        + mcpc_rd_sc  @ a_rd
        + mcpc_rrs_sc @ a_rrs
        + mcpc_ecrs_sc @ a_ecrs
        + mcpc_ns_sc  @ a_ns
        + term_val_p  * s_pu[T]
    )
    all_pu = cp.hstack([d_pu, c_pu, a_ru, a_rd, a_rrs, a_ecrs, a_ns])
    objective = cp.Maximize(rev_pu - eps * cp.sum_squares(all_pu))

    problem = cp.Problem(objective, constraints)
    assert problem.is_dcp(), "Per-unit BESS QP failed DCP check"

    return CvxpyLayer(
        problem,
        parameters=[
            lmp_sc, mcpc_ru_sc, mcpc_rd_sc, mcpc_rrs_sc,
            mcpc_ecrs_sc, mcpc_ns_sc, s0_pu_p, term_val_p,
        ],
        variables=[d_pu, c_pu, a_ru, a_rd, a_rrs, a_ecrs, a_ns, s_pu],
    )


class BESSQPLayer:
    """Differentiable BESS QP with per-unit internals; physical-unit I/O.

    Call signature matches the old CvxpyLayer (positional args + solver_args):

        layer = BESSQPLayer(bess)
        d, c, a_ru, a_rd, a_rrs, a_ecrs, a_ns, s = layer(
            lmp, mcpc_ru, mcpc_rd, mcpc_rrs, mcpc_ecrs, mcpc_ns, s0, term_lmp,
            solver_args={"max_iters": 10000, "eps": 1e-6},
        )

    All inputs and outputs are in physical units: power in MW, energy in MWh,
    prices in $/MWh.  The per-unit conversion is transparent.
    """

    def __init__(
        self,
        bess: BESSParams,
        T: int = T_TRAIN,
        eps: float = EPS,
    ) -> None:
        self.P  = bess.power_mw
        self.E  = bess.soc_energy_max
        self.dt = bess.dt_hours

        ratio       = self.dt * self.P / self.E
        nspin_ratio = bess.nspin_soc_hours * self.P / self.E
        s_min_pu    = bess.soc_energy_min / self.E

        self._layer = _build_pu_layer(
            ratio=ratio,
            rte=bess.rte,
            nspin_ratio=nspin_ratio,
            s_min_pu=s_min_pu,
            T=T,
            eps=eps,
        )
        self._scale = self.dt * self.P  # $/MWh → $ per per-unit interval

    def __call__(
        self,
        lmp: torch.Tensor,
        mcpc_ru: torch.Tensor,
        mcpc_rd: torch.Tensor,
        mcpc_rrs: torch.Tensor,
        mcpc_ecrs: torch.Tensor,
        mcpc_ns: torch.Tensor,
        s0: torch.Tensor,
        term_lmp: torch.Tensor,
        **kwargs,
    ) -> tuple[torch.Tensor, ...]:
        sc = self._scale
        lmp_sc       = lmp       * sc
        mcpc_ru_sc   = mcpc_ru   * sc
        mcpc_rd_sc   = mcpc_rd   * sc
        mcpc_rrs_sc  = mcpc_rrs  * sc
        mcpc_ecrs_sc = mcpc_ecrs * sc
        mcpc_ns_sc   = mcpc_ns   * sc
        s0_pu        = s0        / self.E
        term_val     = term_lmp  * self.E

        outs = self._layer(
            lmp_sc, mcpc_ru_sc, mcpc_rd_sc, mcpc_rrs_sc,
            mcpc_ecrs_sc, mcpc_ns_sc, s0_pu, term_val,
            **kwargs,
        )
        d_pu, c_pu, a_ru_pu, a_rd_pu, a_rrs_pu, a_ecrs_pu, a_ns_pu, s_pu = outs
        return (
            d_pu    * self.P,
            c_pu    * self.P,
            a_ru_pu * self.P,
            a_rd_pu * self.P,
            a_rrs_pu * self.P,
            a_ecrs_pu * self.P,
            a_ns_pu * self.P,
            s_pu    * self.E,
        )
