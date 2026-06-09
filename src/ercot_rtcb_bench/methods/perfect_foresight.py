"""Perfect-foresight BESS LP baseline (Task 4).

Optimizes BESS dispatch over a price window with full knowledge of all
future RT clearing prices (LMP + AS MCPCs). Provides an upper bound on
achievable revenue under any causal strategy.

Formulation:
  - LP (no binary variables; simultaneous charge+discharge is suboptimal)
  - Variables per interval t: discharge d_t, charge c_t, AS awards (5 products),
    SoC s_t in MWh
  - Objective: maximize sum_t dt × [lmp_t × (d_t - c_t) + Σ mcpc_pt × a_pt]
  - Constraints:
      SOC dynamics: s_{t+1} = s_t - dt × d_t + dt × rte × c_t
      Discharge side: d_t + a_regup + a_rrs + a_ecrs + a_nspin ≤ P
      Charge side: c_t + a_regdn ≤ P
      NSPIN SOC: s_t ≥ nspin_soc_hours × a_nspin_t (ADR 0004 / NPRR 1096)
      SOC bounds: E × soc_min ≤ s_t ≤ E × soc_max
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np
import pandas as pd

from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.solver import LPSolution, solve

logger = logging.getLogger(__name__)

# Column names in the price DataFrame
_PRICE_COLS = ["lmp", "mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]
# Variable order within each interval block: [d, c, a_ru, a_rd, a_rrs, a_ecrs, a_ns, s]
_D, _C, _ARU, _ARD, _ARRS, _AECRS, _ANS, _S = range(8)
_VARS_PER_INTERVAL = 7  # d, c, 5 AS awards (SoC s_t is a separate block)


class PerfectForesightResult(NamedTuple):
    dispatch: pd.DataFrame  # per-interval decisions
    revenue_total: float    # total $ revenue over the window
    revenue_energy: float
    revenue_as: float
    solution: LPSolution


def perfect_foresight(
    params: BESSParams,
    prices: pd.DataFrame,
    solver_kwargs: dict | None = None,
    terminal_lmp: float = 0.0,
) -> PerfectForesightResult:
    """Run perfect-foresight LP optimization.

    Args:
        params: BESS physical parameters.
        prices: DataFrame indexed by timestamp_utc with columns
                [lmp, mcpc_regup, mcpc_regdn, mcpc_rrs, mcpc_ecrs, mcpc_nspin].
                All MCPCs must be ≥ 0; LMP may be negative.
        solver_kwargs: Passed to solver.solve().

    Returns:
        PerfectForesightResult with per-interval dispatch and revenue breakdown.
    """
    missing = [c for c in _PRICE_COLS if c not in prices.columns]
    if missing:
        raise ValueError(f"prices DataFrame missing columns: {missing}")

    prices = prices[_PRICE_COLS].dropna()
    T = len(prices)
    if T == 0:
        raise ValueError("prices DataFrame is empty after dropna()")

    P = params.power_mw
    E = params.energy_mwh
    rte = params.rte
    dt = params.dt_hours
    nspin_h = params.nspin_soc_hours
    s_init = params.soc_energy_init
    s_min = params.soc_energy_min
    s_max = params.soc_energy_max

    lmp = prices["lmp"].values
    mcpc_ru = prices["mcpc_regup"].values
    mcpc_rd = prices["mcpc_regdn"].values
    mcpc_rrs = prices["mcpc_rrs"].values
    mcpc_ecrs = prices["mcpc_ecrs"].values
    mcpc_ns = prices["mcpc_nspin"].values

    # Variable layout: [d_0..d_{T-1}, c_0..c_{T-1}, a_ru_0..., a_rd_0...,
    #                   a_rrs_0..., a_ecrs_0..., a_ns_0..., s_0..s_T]
    # Block offsets:
    i_d = 0
    i_c = T
    i_ru = 2 * T
    i_rd = 3 * T
    i_rrs = 4 * T
    i_ecrs = 5 * T
    i_ns = 6 * T
    i_s = 7 * T
    N = 7 * T + (T + 1)  # total variables (incl. s_0..s_T)

    # ── Objective (minimize -revenue) ─────────────────────────────────────────
    c_obj = np.zeros(N)
    c_obj[i_d: i_d + T] = -lmp * dt        # -discharge revenue
    c_obj[i_c: i_c + T] = lmp * dt         # +charge cost
    c_obj[i_ru: i_ru + T] = -mcpc_ru * dt
    c_obj[i_rd: i_rd + T] = -mcpc_rd * dt
    c_obj[i_rrs: i_rrs + T] = -mcpc_rrs * dt
    c_obj[i_ecrs: i_ecrs + T] = -mcpc_ecrs * dt
    c_obj[i_ns: i_ns + T] = -mcpc_ns * dt
    # Terminal value: +terminal_lmp × s_T (index i_s + T is s_T)
    if terminal_lmp != 0.0:
        c_obj[i_s + T] -= terminal_lmp

    # ── Equality constraints: SoC dynamics ───────────────────────────────────
    # s_{t+1} - s_t + dt * d_t - dt * rte * c_t = 0  for t = 0..T-1
    # Plus: s_0 = s_init
    A_eq = np.zeros((T + 1, N))
    b_eq = np.zeros(T + 1)

    # s_0 = s_init
    A_eq[0, i_s] = 1.0
    b_eq[0] = s_init

    for t in range(T):
        row = t + 1
        A_eq[row, i_s + t] = -1.0           # -s_t
        A_eq[row, i_s + t + 1] = 1.0         # +s_{t+1}
        A_eq[row, i_d + t] = dt              # +dt * d_t
        A_eq[row, i_c + t] = -dt * rte       # -dt * rte * c_t
        b_eq[row] = 0.0

    # ── Inequality constraints ────────────────────────────────────────────────
    # 1. Discharge side: d_t + a_ru_t + a_rrs_t + a_ecrs_t + a_ns_t ≤ P
    # 2. Charge side: c_t + a_rd_t ≤ P
    # 3. NSPIN SOC: -s_t + nspin_h * a_ns_t ≤ 0  (for t = 0..T-1)
    n_ineq = 3 * T
    A_ub = np.zeros((n_ineq, N))
    b_ub = np.zeros(n_ineq)

    for t in range(T):
        # Discharge side
        r_dis = t
        A_ub[r_dis, i_d + t] = 1.0
        A_ub[r_dis, i_ru + t] = 1.0
        A_ub[r_dis, i_rrs + t] = 1.0
        A_ub[r_dis, i_ecrs + t] = 1.0
        A_ub[r_dis, i_ns + t] = 1.0
        b_ub[r_dis] = P

        # Charge side
        r_chg = T + t
        A_ub[r_chg, i_c + t] = 1.0
        A_ub[r_chg, i_rd + t] = 1.0
        b_ub[r_chg] = P

        # NSPIN SOC: -s_t + nspin_h * a_ns_t ≤ 0
        r_ns = 2 * T + t
        A_ub[r_ns, i_s + t] = -1.0
        A_ub[r_ns, i_ns + t] = nspin_h
        b_ub[r_ns] = 0.0

    # ── Variable bounds ───────────────────────────────────────────────────────
    bounds = (
        [(0.0, P)] * T       # d_t
        + [(0.0, P)] * T     # c_t
        + [(0.0, P)] * T     # a_ru
        + [(0.0, P)] * T     # a_rd
        + [(0.0, P)] * T     # a_rrs
        + [(0.0, P)] * T     # a_ecrs
        + [(0.0, P)] * T     # a_ns
        + [(s_min, s_max)] * (T + 1)  # s_t
    )

    # ── Solve ─────────────────────────────────────────────────────────────────
    logger.info(
        "Perfect-foresight LP: T=%d, N=%d vars, %d eq, %d ineq",
        T, N, len(b_eq), len(b_ub),
    )
    sol = solve(c_obj, A_ub, b_ub, A_eq, b_eq, bounds, **(solver_kwargs or {}))
    logger.info("Solved by %s: obj=%.2f, status=%s", sol.solver, sol.objective, sol.status)

    # ── Extract results ───────────────────────────────────────────────────────
    x = sol.x
    d = x[i_d: i_d + T]
    c_ = x[i_c: i_c + T]
    a_ru = x[i_ru: i_ru + T]
    a_rd = x[i_rd: i_rd + T]
    a_rrs = x[i_rrs: i_rrs + T]
    a_ecrs = x[i_ecrs: i_ecrs + T]
    a_ns = x[i_ns: i_ns + T]
    soc = x[i_s: i_s + T + 1][:-1]  # s_0..s_{T-1} (SoC at start of each interval)

    net_energy = d - c_
    rev_energy = lmp * net_energy * dt
    rev_as = (mcpc_ru * a_ru + mcpc_rd * a_rd + mcpc_rrs * a_rrs
              + mcpc_ecrs * a_ecrs + mcpc_ns * a_ns) * dt

    dispatch = pd.DataFrame(
        {
            "timestamp_utc": prices.index,
            "discharge_mw": d,
            "charge_mw": c_,
            "net_energy_mw": net_energy,
            "award_regup_mw": a_ru,
            "award_regdn_mw": a_rd,
            "award_rrs_mw": a_rrs,
            "award_ecrs_mw": a_ecrs,
            "award_nspin_mw": a_ns,
            "soc_mwh": soc,
            "soc_frac": soc / E,
            "revenue_energy_usd": rev_energy,
            "revenue_as_usd": rev_as,
            "revenue_total_usd": rev_energy + rev_as,
            "lmp": lmp,
            "mcpc_regup": mcpc_ru,
            "mcpc_regdn": mcpc_rd,
            "mcpc_rrs": mcpc_rrs,
            "mcpc_ecrs": mcpc_ecrs,
            "mcpc_nspin": mcpc_ns,
        }
    ).set_index("timestamp_utc")

    return PerfectForesightResult(
        dispatch=dispatch,
        revenue_total=float(rev_energy.sum() + rev_as.sum()),
        revenue_energy=float(rev_energy.sum()),
        revenue_as=float(rev_as.sum()),
        solution=sol,
    )
