"""Two-stage stochastic LP for BESS dispatch — W3-C method.

Uses gurobipy MVar for vectorized constraint construction.
Stage 1: first hour (T1=12 intervals), shared decisions.
Stage 2: remaining 23h (T2=276 intervals), per-scenario recourse.
"""

from __future__ import annotations

import time

import numpy as np

from ercot_rtcb_bench.methods.battery import BESSParams

T1_DEFAULT = 12
T2_DEFAULT = 276


def solve_stochastic_hour(
    stage1_prices: np.ndarray,
    stage2_scenarios: np.ndarray,
    probabilities: np.ndarray,
    bess: BESSParams,
    s_init: float,
    seed: int = 42,
    mip_gap: float = 0.001,
    time_limit: float = 120.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Solve stochastic LP for one rolling-horizon hour.

    Args:
        stage1_prices: [T1, 6] array — stage-1 price expectations (mean over scenarios).
        stage2_scenarios: [K, T2, 6] array — stage-2 scenario prices.
        probabilities: [K] scenario weights summing to 1.
        bess: BESS physical parameters.
        s_init: Initial SoC in MWh.
        seed: Random seed (unused in LP, kept for API consistency).
        mip_gap: Gurobi MIPGap (LP so unused, but passed).
        time_limit: Solver time limit in seconds.

    Returns:
        (d1, c1, a_ru1, a_rd1, a_rrs1, a_ecrs1, a_ns1, s1_end, obj_val, solve_time)
        where each of d1..a_ns1 is shape [T1], s1_end is scalar MWh,
        obj_val is the LP's optimal expected total revenue (RP, for in-expectation VSS),
        and solve_time is seconds.
    """
    import gurobipy as gp
    from gurobipy import GRB

    K, T2, _ = stage2_scenarios.shape
    T1 = stage1_prices.shape[0]

    P = bess.power_mw
    rte = bess.rte
    dt = bess.dt_hours
    nspin_h = bess.nspin_soc_hours
    s_min = bess.soc_energy_min
    s_max = bess.soc_energy_max

    # Stage-1 prices: use probability-weighted mean across scenarios for each interval
    # stage1_prices is already the mean (caller may pass scenario mean or point forecast)
    lmp1 = stage1_prices[:, 0]
    ru1 = stage1_prices[:, 1]
    rd1 = stage1_prices[:, 2]
    rrs1 = stage1_prices[:, 3]
    ecrs1 = stage1_prices[:, 4]
    ns1 = stage1_prices[:, 5]

    t0 = time.perf_counter()

    m = gp.Model()
    m.setParam("OutputFlag", 0)
    m.setParam("MIPGap", mip_gap)
    m.setParam("TimeLimit", time_limit)

    # ── Stage 1 variables ─────────────────────────────────────────────────────
    d1 = m.addMVar(T1, lb=0.0, ub=P, name="d1")
    c1 = m.addMVar(T1, lb=0.0, ub=P, name="c1")
    a_ru1 = m.addMVar(T1, lb=0.0, ub=P, name="a_ru1")
    a_rd1 = m.addMVar(T1, lb=0.0, ub=P, name="a_rd1")
    a_rrs1 = m.addMVar(T1, lb=0.0, ub=P, name="a_rrs1")
    a_ecrs1 = m.addMVar(T1, lb=0.0, ub=P, name="a_ecrs1")
    a_ns1 = m.addMVar(T1, lb=0.0, ub=P, name="a_ns1")
    s1 = m.addMVar(T1 + 1, lb=s_min, ub=s_max, name="s1")

    # ── Stage 2 variables (K scenarios) ──────────────────────────────────────
    d2 = m.addMVar((K, T2), lb=0.0, ub=P, name="d2")
    c2 = m.addMVar((K, T2), lb=0.0, ub=P, name="c2")
    a_ru2 = m.addMVar((K, T2), lb=0.0, ub=P, name="a_ru2")
    a_rd2 = m.addMVar((K, T2), lb=0.0, ub=P, name="a_rd2")
    a_rrs2 = m.addMVar((K, T2), lb=0.0, ub=P, name="a_rrs2")
    a_ecrs2 = m.addMVar((K, T2), lb=0.0, ub=P, name="a_ecrs2")
    a_ns2 = m.addMVar((K, T2), lb=0.0, ub=P, name="a_ns2")
    s2 = m.addMVar((K, T2 + 1), lb=s_min, ub=s_max, name="s2")

    # ── Stage 1 constraints ───────────────────────────────────────────────────
    m.addConstr(s1[0] == s_init)
    m.addConstr(s1[1:] - s1[:-1] + dt * d1 - dt * rte * c1 == 0)
    m.addConstr(d1 + a_ru1 + a_rrs1 + a_ecrs1 + a_ns1 <= P)
    m.addConstr(c1 + a_rd1 <= P)
    m.addConstr(nspin_h * a_ns1 - s1[:-1] <= 0)

    # ── Stage 2 constraints (vectorized per scenario) ─────────────────────────
    for k in range(K):
        # Non-anticipativity: s2[k,0] = s1[T1]
        m.addConstr(s2[k, 0] == s1[T1])
        # SoC dynamics
        m.addConstr(s2[k, 1:] - s2[k, :-1] + dt * d2[k] - dt * rte * c2[k] == 0)
        # Power limits
        m.addConstr(d2[k] + a_ru2[k] + a_rrs2[k] + a_ecrs2[k] + a_ns2[k] <= P)
        m.addConstr(c2[k] + a_rd2[k] <= P)
        # NSPIN SoC: uses SoC at START of interval
        m.addConstr(nspin_h * a_ns2[k] - s2[k, :-1] <= 0)

    # ── Objective ─────────────────────────────────────────────────────────────
    # Build as MLinExpr using numpy coefficient arrays; negate for minimization.
    # Stage 1 revenue (coeff arrays × MVar)
    rev1 = (
        (lmp1 * dt) @ d1
        - (lmp1 * dt) @ c1
        + (ru1 * dt) @ a_ru1
        + (rd1 * dt) @ a_rd1
        + (rrs1 * dt) @ a_rrs1
        + (ecrs1 * dt) @ a_ecrs1
        + (ns1 * dt) @ a_ns1
    )

    # Stage 2 revenue accumulated as MLinExpr
    rev2 = None
    for k in range(K):
        pk = float(probabilities[k])
        lmp2k = stage2_scenarios[k, :, 0]
        ru2k = stage2_scenarios[k, :, 1]
        rd2k = stage2_scenarios[k, :, 2]
        rrs2k = stage2_scenarios[k, :, 3]
        ecrs2k = stage2_scenarios[k, :, 4]
        ns2k = stage2_scenarios[k, :, 5]

        term = (
            (pk * dt * lmp2k) @ d2[k]
            - (pk * dt * lmp2k) @ c2[k]
            + (pk * dt * ru2k) @ a_ru2[k]
            + (pk * dt * rd2k) @ a_rd2[k]
            + (pk * dt * rrs2k) @ a_rrs2[k]
            + (pk * dt * ecrs2k) @ a_ecrs2[k]
            + (pk * dt * ns2k) @ a_ns2[k]
        )
        # Terminal value: pk × mean(lmp2k) × s2[k, T2]
        terminal_lmp_k = float(lmp2k.mean())
        term = term + (pk * terminal_lmp_k) * s2[k, T2]

        rev2 = term if rev2 is None else rev2 + term

    total_rev = rev1 + rev2 if rev2 is not None else rev1
    m.setObjective(-total_rev, GRB.MINIMIZE)

    m.optimize()

    if m.status not in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
        raise RuntimeError(f"Gurobi status {m.status} — stochastic LP not optimal")

    solve_time = time.perf_counter() - t0
    # m minimizes -total_rev, so ObjVal = -total_rev → RP = -ObjVal
    obj_val = -float(m.ObjVal)

    return (
        np.array(d1.X),
        np.array(c1.X),
        np.array(a_ru1.X),
        np.array(a_rd1.X),
        np.array(a_rrs1.X),
        np.array(a_ecrs1.X),
        np.array(a_ns1.X),
        float(s1.X[T1]),
        obj_val,
        solve_time,
    )
