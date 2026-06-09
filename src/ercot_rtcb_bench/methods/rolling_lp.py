"""Rolling-horizon LP wrapper shared by deterministic and stochastic methods."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.perfect_foresight import _PRICE_COLS, perfect_foresight

_AS_COLS = ["mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]

T1 = 12   # stage-1 intervals (first committed hour)
T2 = 276  # stage-2 intervals (remaining 23h recourse)


@dataclass
class HourResult:
    hour_utc: pd.Timestamp
    revenue_energy_usd: float
    revenue_as_usd: float
    dispatch: pd.DataFrame  # 12-row committed 5-min decisions


@dataclass
class RollingResult:
    hours: list[HourResult]
    revenue_total: float
    revenue_energy: float
    revenue_as: float
    liquidation_revenue: float
    wall_clock_s: float
    solver_times_s: list[float]


def _settle_hour(
    dispatch: pd.DataFrame,
    rt_prices: pd.DataFrame,
    dt: float,
) -> tuple[float, float, pd.DataFrame]:
    """Settle 12-interval dispatch block at actual RT prices.

    Returns (rev_energy, rev_as, dispatch_with_rt_prices).
    """
    idx = dispatch.index
    rt = rt_prices.reindex(idx, method="nearest")

    lmp_rt = rt["lmp"].values
    ru_rt = rt["mcpc_regup"].values
    rd_rt = rt["mcpc_regdn"].values
    rrs_rt = rt["mcpc_rrs"].values
    ecrs_rt = rt["mcpc_ecrs"].values
    ns_rt = rt["mcpc_nspin"].values

    net = dispatch["discharge_mw"].values - dispatch["charge_mw"].values
    rev_energy = float((lmp_rt * net * dt).sum())
    rev_as = float((
        ru_rt * dispatch["award_regup_mw"].values
        + rd_rt * dispatch["award_regdn_mw"].values
        + rrs_rt * dispatch["award_rrs_mw"].values
        + ecrs_rt * dispatch["award_ecrs_mw"].values
        + ns_rt * dispatch["award_nspin_mw"].values
    ).sum() * dt)

    d = dispatch.copy()
    d["lmp_rt"] = lmp_rt
    return rev_energy, rev_as, d


def run_rolling_lp(
    bess: BESSParams,
    rt_prices: pd.DataFrame,
    get_lookahead_fn,
    solve_hour_fn,
    panel_start: pd.Timestamp,
    panel_end: pd.Timestamp,
) -> RollingResult:
    """Run rolling-horizon LP over [panel_start, panel_end).

    Args:
        bess: BESS physical parameters.
        rt_prices: 5-min RT prices indexed by timestamp_utc (for settlement).
        get_lookahead_fn: callable(hour_utc) -> dict with 'stage1' and 'stage2' keys.
        solve_hour_fn: callable(lookahead, s_init) -> (decisions_df [12 rows], s_next, solve_time).
        panel_start: First hour (inclusive).
        panel_end: Last hour (exclusive).

    Returns:
        RollingResult with per-hour details and aggregate revenue.
    """
    t_wall_start = time.perf_counter()
    dt = bess.dt_hours
    rte = bess.rte

    hours = pd.date_range(panel_start, panel_end, freq="h", inclusive="left")
    s_current = bess.soc_energy_init

    hour_results: list[HourResult] = []
    solver_times: list[float] = []

    for h in hours:
        lookahead = get_lookahead_fn(h)
        decisions, _s_lp, solve_time = solve_hour_fn(lookahead, s_current)
        solver_times.append(solve_time)

        # Settle at RT prices
        rev_e, rev_as, disp_rt = _settle_hour(decisions, rt_prices, dt)

        # Advance SoC using audited formula (not LP's internal SoC)
        d_vec = decisions["discharge_mw"].values
        c_vec = decisions["charge_mw"].values
        s_current = s_current - dt * d_vec.sum() + dt * rte * c_vec.sum()
        s_current = float(np.clip(s_current, bess.soc_energy_min, bess.soc_energy_max))

        hour_results.append(HourResult(
            hour_utc=h,
            revenue_energy_usd=rev_e,
            revenue_as_usd=rev_as,
            dispatch=disp_rt,
        ))

    # End-of-window SoC liquidation
    final_ts = panel_end - pd.Timedelta("5min")
    final_lmp = float(rt_prices.loc[final_ts, "lmp"]) if final_ts in rt_prices.index else float(
        rt_prices.iloc[-1]["lmp"]
    )
    liquidation_rev = s_current * final_lmp

    total_energy = sum(r.revenue_energy_usd for r in hour_results)
    total_as = sum(r.revenue_as_usd for r in hour_results)

    return RollingResult(
        hours=hour_results,
        revenue_total=total_energy + total_as + liquidation_rev,
        revenue_energy=total_energy,
        revenue_as=total_as,
        liquidation_revenue=liquidation_rev,
        wall_clock_s=time.perf_counter() - t_wall_start,
        solver_times_s=solver_times,
    )


def solve_deterministic_hour(
    lookahead: dict,
    bess: BESSParams,
    s_init: float,
) -> tuple[pd.DataFrame, float, float]:
    """Solve deterministic LP over 24h; return committed first-hour decisions, s_next, solve_time.

    lookahead dict keys:
        'stage1': pd.DataFrame [12 rows, _PRICE_COLS] (DAM prices, first hour)
        'stage2': pd.DataFrame [276 rows, _PRICE_COLS] (DAM prices, remaining 23h)
        'terminal_lmp': float
    """
    stage1: pd.DataFrame = lookahead["stage1"]
    stage2: pd.DataFrame = lookahead["stage2"]
    terminal_lmp: float = lookahead.get("terminal_lmp", 0.0)

    prices_24h = pd.concat([stage1, stage2])

    # Override s_init in bess params (create temporary copy)
    import copy
    bess_h = copy.copy(bess)
    bess_h.soc_init = s_init / bess.energy_mwh

    t0 = time.perf_counter()
    result = perfect_foresight(bess_h, prices_24h, terminal_lmp=terminal_lmp)
    solve_time = time.perf_counter() - t0

    # Extract first T1 rows of dispatch
    first_hour = result.dispatch.iloc[:T1].copy()

    # Rename columns to expected names
    dispatch = pd.DataFrame({
        "discharge_mw": first_hour["discharge_mw"].values,
        "charge_mw": first_hour["charge_mw"].values,
        "award_regup_mw": first_hour["award_regup_mw"].values,
        "award_regdn_mw": first_hour["award_regdn_mw"].values,
        "award_rrs_mw": first_hour["award_rrs_mw"].values,
        "award_ecrs_mw": first_hour["award_ecrs_mw"].values,
        "award_nspin_mw": first_hour["award_nspin_mw"].values,
    }, index=first_hour.index)

    # s_next from LP's internal SoC (not used for carry-forward, but returned for info)
    s_next = float(result.dispatch.iloc[T1 - 1]["soc_mwh"]) if len(result.dispatch) >= T1 else s_init

    return dispatch, s_next, solve_time
