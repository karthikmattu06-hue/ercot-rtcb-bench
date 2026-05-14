"""LP/MILP solver interface: Gurobi primary, HiGHS fallback, scipy last resort.

Usage:
    sol = solve(c, A_ub, b_ub, A_eq, b_eq, bounds)
    sol = solve(c, A_ub, b_ub, A_eq, b_eq, bounds, integrality=integ_vec)

All matrices/vectors are numpy arrays or scipy sparse. The objective is
minimization; callers negate the revenue vector to maximize.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np

logger = logging.getLogger(__name__)


class LPSolution(NamedTuple):
    x: np.ndarray
    objective: float  # minimized objective value (negated revenue for LP)
    solver: str
    status: str
    mip_gap: float | None = None


def solve(
    c: np.ndarray,
    A_ub: np.ndarray | None,
    b_ub: np.ndarray | None,
    A_eq: np.ndarray | None,
    b_eq: np.ndarray | None,
    bounds: list[tuple[float | None, float | None]],
    integrality: np.ndarray | None = None,
    mip_gap: float = 0.001,
    time_limit: float = 300.0,
) -> LPSolution:
    """Solve an LP or MILP. Tries Gurobi, then HiGHS, then scipy.optimize.

    Args:
        c: Objective coefficient vector (minimized).
        A_ub: Inequality constraint matrix (A_ub @ x ≤ b_ub).
        b_ub: Inequality RHS.
        A_eq: Equality constraint matrix (A_eq @ x = b_eq).
        b_eq: Equality RHS.
        bounds: List of (lb, ub) per variable.
        integrality: 0/1 vector; 1 = integer variable. None → pure LP.
        mip_gap: Relative MIP optimality gap (Gurobi/HiGHS only).
        time_limit: Solver time limit in seconds.

    Returns:
        LPSolution with optimal x, objective value, solver name, and status.
    """
    is_milp = integrality is not None and np.any(integrality)

    try:
        return _solve_gurobi(c, A_ub, b_ub, A_eq, b_eq, bounds, integrality, mip_gap, time_limit)
    except ImportError:
        logger.debug("Gurobi not available; trying HiGHS")
    except Exception as e:
        logger.warning("Gurobi failed (%s); trying HiGHS", e)

    try:
        return _solve_highs(c, A_ub, b_ub, A_eq, b_eq, bounds, integrality, mip_gap, time_limit)
    except ImportError:
        logger.debug("HiGHS not available; falling back to scipy")
    except Exception as e:
        logger.warning("HiGHS failed (%s); falling back to scipy", e)

    if is_milp:
        raise RuntimeError(
            "Neither Gurobi nor HiGHS is available; cannot solve MILP. "
            "Install gurobipy or highspy."
        )
    return _solve_scipy(c, A_ub, b_ub, A_eq, b_eq, bounds)


# ── Gurobi ────────────────────────────────────────────────────────────────────


def _solve_gurobi(c, A_ub, b_ub, A_eq, b_eq, bounds, integrality, mip_gap, time_limit):
    import gurobipy as gp
    from gurobipy import GRB

    m = gp.Model()
    m.setParam("OutputFlag", 0)
    m.setParam("MIPGap", mip_gap)
    m.setParam("TimeLimit", time_limit)

    n = len(c)
    lb = np.array([b[0] if b[0] is not None else -GRB.INFINITY for b in bounds])
    ub = np.array([b[1] if b[1] is not None else GRB.INFINITY for b in bounds])

    vtype = [
        (GRB.BINARY if (integrality is not None and integrality[i] == 1) else GRB.CONTINUOUS)
        for i in range(n)
    ]
    x = m.addMVar(n, lb=lb, ub=ub, vtype=vtype, name="x")
    m.setObjective(c @ x, GRB.MINIMIZE)

    if A_ub is not None and len(b_ub) > 0:
        m.addConstr(A_ub @ x <= b_ub)
    if A_eq is not None and len(b_eq) > 0:
        m.addConstr(A_eq @ x == b_eq)

    m.optimize()

    if m.status in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
        gap = m.MIPGap if m.isMIP else None
        return LPSolution(
            x=np.array(x.X),
            objective=float(m.ObjVal),
            solver="gurobi",
            status="optimal" if m.status == GRB.OPTIMAL else "suboptimal",
            mip_gap=gap,
        )
    raise RuntimeError(f"Gurobi status {m.status} — not optimal")


# ── HiGHS ─────────────────────────────────────────────────────────────────────


def _solve_highs(c, A_ub, b_ub, A_eq, b_eq, bounds, integrality, mip_gap, time_limit):
    import highspy

    h = highspy.Highs()
    h.silent()

    n = len(c)
    lb = np.array([b[0] if b[0] is not None else -1e30 for b in bounds])
    ub = np.array([b[1] if b[1] is not None else 1e30 for b in bounds])

    h.addVars(n, lb, ub)
    h.changeColsCostByRange(0, n - 1, c)

    if integrality is not None:
        for i, ig in enumerate(integrality):
            if ig == 1:
                h.changeColIntegrality(i, highspy.kInteger)

    h.setOptionValue("mip_rel_gap", mip_gap)
    h.setOptionValue("time_limit", time_limit)

    # Add inequality constraints row-by-row (sparse-friendly)
    if A_ub is not None:
        for i, (row, rhs) in enumerate(zip(A_ub, b_ub)):
            nz_idx = np.nonzero(row)[0]
            h.addRow(-1e30, float(rhs), len(nz_idx), nz_idx.tolist(),
                     row[nz_idx].tolist())

    if A_eq is not None:
        for i, (row, rhs) in enumerate(zip(A_eq, b_eq)):
            nz_idx = np.nonzero(row)[0]
            h.addRow(float(rhs), float(rhs), len(nz_idx), nz_idx.tolist(),
                     row[nz_idx].tolist())

    h.run()
    info = h.getInfoValue("primal_solution_status")[1]
    sol = h.getSolution()
    obj = h.getInfoValue("objective_function_value")[1]

    if info in (2, 3):  # feasible or optimal
        return LPSolution(
            x=np.array(sol.col_value),
            objective=float(obj),
            solver="highs",
            status="optimal" if info == 3 else "feasible",
        )
    raise RuntimeError(f"HiGHS primal status {info} — not feasible")


# ── scipy fallback (LP only) ──────────────────────────────────────────────────


def _solve_scipy(c, A_ub, b_ub, A_eq, b_eq, bounds):
    from scipy.optimize import linprog

    res = linprog(
        c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if res.status == 0:
        return LPSolution(
            x=res.x,
            objective=float(res.fun),
            solver="scipy-highs",
            status="optimal",
        )
    raise RuntimeError(f"scipy.linprog failed: {res.message}")
