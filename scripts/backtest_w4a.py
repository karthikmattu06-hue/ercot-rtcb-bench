"""W4-A: Realized-gap attribution — LMP bias vs AS effective-price correction.

Decomposes the Stochastic-LP → PF headroom ($113,236) into four legs:
  ΔLMP     : revenue gain from oracle LMP (per-hour mean centering, no clip)
  ΔAS      : revenue gain from oracle AS  (E[max] retargeting to realized)
  Interaction
  Residual : PF − CF-AB

Oracle definitions (per ADR 0010):

  CF-A (unchanged): per-hour LMP scenario mean shifted to realized.
    Additive shift, no clip. Stage-1 and stage-2 LMP both corrected.

  CF-B (E[max] retarget): for each AS product p and operating hour h, find
    the additive shift δ(p,h) solving
        mean_t( E_k[ max(scenario_k(p,t) + δ, 0) ] ) = realized_mean(RT_MCPC_p, h)
    via bisection.  No data-layer clip — max(·,0) is inside the target, matching
    what the stage-2 LP actually plans on (awards ≥ 0, per-scenario recourse).
    Rationale: realized RT MCPC ≥ 0, so realized mean = realized E[max(·,0)];
    oracle sets the LP's effective AS price perception equal to realized.

    Edge cases:
      realized_mean < $0.01: set (product,hour) scenarios to 0 directly (no root).
      |δ| > $500/MWh equivalent: cap and log (should be rare).

  CF-AB: both CF-A + CF-B applied simultaneously.

  Stage-1 caveat: stage-1 (4.2% of horizon, T1=12 intervals) prices AS on the
  raw probability-weighted mean of shifted scenarios, not on E[max(·,0)].  The
  E[max] oracle implies a small raw-mean undershoot for stage-1 AS; bounded by
  the 4.2% share.  Noted, not engineered around.

  CF-A / ΔLMP=$21,479 / Baseline=$238,376 reused from prior run — not re-run.
"""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.forecaster.forecaster import BootstrapForecaster
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.perfect_foresight import _PRICE_COLS
from ercot_rtcb_bench.methods.rolling_lp import T1, T2, run_rolling_lp
from ercot_rtcb_bench.methods.stochastic_lp import solve_stochastic_hour

PANEL_START    = pd.Timestamp("2026-04-20 00:00", tz="UTC")
PANEL_END      = pd.Timestamp("2026-04-27 00:00", tz="UTC")
CANONICAL_SEED = 42
AUDIT_DIR      = Path(__file__).parent.parent / "data" / "audit"
DATA_DIR       = Path(__file__).parent.parent / "data" / "processed" / "forecaster"
BESS           = BESSParams.default_100mw_4hr()

# Price column order: [lmp, regup, regdn, rrs, ecrs, nspin]
_AS_IDX    = [1, 2, 3, 4, 5]
_AS_NAMES  = ["regup", "regdn", "rrs", "ecrs", "nspin"]
_NEAR_ZERO = 0.01   # realized_mean threshold below which scenarios zeroed
_DELTA_CAP = 500.0  # hard cap on |δ| ($/MWh equivalent)
_BISECT_TOL = 0.001 # convergence tolerance for E[max] root-find

# ── Frozen results from prior CF-A / baseline runs ───────────────────────────
_BASELINE_REVENUE = 238_376.27
_CFA_REVENUE      = 259_855.23
_DELTA_LMP        = _CFA_REVENUE - _BASELINE_REVENUE   # = $21,478.96
_PF_REVENUE       = 351_612.00

# ── Data loading ──────────────────────────────────────────────────────────────

def load_rt_prices() -> pd.DataFrame:
    parts = []
    for m in ["2026-04", "2026-05"]:
        p = DATA_DIR / "rt_prices" / f"{m}.parquet"
        df = pd.read_parquet(p).set_index("timestamp_utc")
        parts.append(df)
    rt = pd.concat(parts).sort_index()
    return rt.ffill().bfill()


# ── Scenario cache (unmodified) ───────────────────────────────────────────────

_dataset = ForecasterDataset()
_fc      = BootstrapForecaster(dataset=_dataset, random_seed=CANONICAL_SEED)


@lru_cache(maxsize=12)
def _get_tree_raw(target_date: date):
    return _fc.forecast(target_date)


def _rt_day_array(rt_prices: pd.DataFrame, d: date) -> np.ndarray:
    """Extract [288, 6] RT price array for a calendar day (UTC midnight to midnight)."""
    idx = pd.date_range(pd.Timestamp(d, tz="UTC"), periods=288, freq="5min")
    return rt_prices.reindex(idx, method="nearest")[_PRICE_COLS].to_numpy(dtype=np.float64)


# ── E[max] bisection oracle ────────────────────────────────────────────────────

def _emax_target(s_vals: np.ndarray, probs: np.ndarray, delta: float) -> float:
    """Compute mean_t( E_k[max(s_k[t] + δ, 0)] ).

    s_vals : [K, 12]  per-scenario per-interval values
    probs  : [K]      probability weights
    """
    return float(probs @ np.maximum(s_vals + delta, 0.0).mean(axis=1))


def _find_emax_delta(
    s_vals: np.ndarray,
    probs: np.ndarray,
    realized_mean: float,
) -> tuple[float, bool, str]:
    """Find δ s.t. mean_t(E_k[max(s+δ, 0)]) = realized_mean via bisection.

    Returns (delta, converged, reason).
    reason is 'ok', 'near_zero', 'cap_hit', or 'bracket_fail'.
    """
    if realized_mean < _NEAR_ZERO:
        # No finite root: target is effectively 0.  Shift all scenarios below 0.
        return -float(s_vals.max()) - 1.0, True, "near_zero"

    # Bracket: lo shifts all values well below 0 → f ≈ 0
    lo = -float(s_vals.max()) - 1.0
    f_lo = _emax_target(s_vals, probs, lo)

    if f_lo >= realized_mean:
        # Shouldn't happen if original scenarios ≥ 0 (pre-clipped by bootstrap).
        # Return lo (maximum downshift) and flag.
        return lo, False, "bracket_fail"

    # hi: shift enough that f > realized_mean
    hi = realized_mean + abs(float(s_vals.min())) + 10.0
    f_hi = _emax_target(s_vals, probs, hi)
    if f_hi < realized_mean:
        hi = _DELTA_CAP
        f_hi = _emax_target(s_vals, probs, hi)
        if f_hi < realized_mean:
            return _DELTA_CAP, False, "cap_hit"

    # Bisection (60 iterations → relative bracket width 2^-60 ≈ machine eps)
    for _ in range(60):
        mid = (lo + hi) * 0.5
        f_mid = _emax_target(s_vals, probs, mid)
        if abs(f_mid - realized_mean) < _BISECT_TOL:
            return mid, True, "ok"
        if f_mid < realized_mean:
            lo = mid
        else:
            hi = mid

    mid = (lo + hi) * 0.5
    converged = abs(_emax_target(s_vals, probs, mid) - realized_mean) < _BISECT_TOL * 10
    return mid, converged, "ok" if converged else "bracket_fail"


# ── Oracle scenario construction ──────────────────────────────────────────────

def _oracle_correct(
    scenarios: np.ndarray,   # [K, 6, 288]
    probs: np.ndarray,       # [K]
    rt_day: np.ndarray,      # [288, 6]
    fix_lmp: bool,
    fix_as: bool,
    edge_log: dict,          # mutated in-place: counts near_zero / cap_hit / nonconv
) -> np.ndarray:
    """Apply per-hour oracle corrections to scenario array.

    LMP (fix_lmp): additive mean centering — no clip.
    AS  (fix_as):  E[max] retargeting via bisection — no data-layer clip.
      Scenarios for near_zero hours are set to 0 directly.
    """
    corrected = scenarios.copy()

    for h in range(24):
        sl = slice(h * 12, (h + 1) * 12)

        if fix_lmp:
            s = corrected[:, 0, sl]                            # [K, 12]
            fc_mean = float(probs @ s.mean(axis=1))
            rt_mean = float(rt_day[sl, 0].mean())
            corrected[:, 0, sl] += (rt_mean - fc_mean)

        if fix_as:
            for p in _AS_IDX:
                s = corrected[:, p, sl]                        # [K, 12]
                rt_mean = float(rt_day[sl, p].mean())

                if rt_mean < _NEAR_ZERO:
                    corrected[:, p, sl] = 0.0
                    edge_log["near_zero"] += 1
                    continue

                delta, converged, reason = _find_emax_delta(s, probs, rt_mean)

                if reason == "cap_hit":
                    edge_log["cap_hit"] += 1
                if not converged:
                    edge_log["nonconv"] += 1

                if reason == "near_zero":
                    corrected[:, p, sl] = 0.0
                else:
                    corrected[:, p, sl] = s + delta
                    # No data-layer clip — max(·,0) lives in LP's planning layer

    return corrected


def _make_get_stochastic_window(
    rt_prices: pd.DataFrame,
    fix_lmp: bool,
    fix_as: bool,
    edge_log: dict,
):
    """Factory: returns a get_stochastic_window with oracle correction applied."""
    oracle_cache: dict[date, np.ndarray] = {}

    def _get_corrected(d: date) -> np.ndarray:
        if d not in oracle_cache:
            tree  = _get_tree_raw(d)
            scen  = tree.scenarios.copy()
            probs = tree.probabilities
            rt_day = _rt_day_array(rt_prices, d)
            oracle_cache[d] = _oracle_correct(scen, probs, rt_day, fix_lmp, fix_as, edge_log)
        return oracle_cache[d]

    def get_stochastic_window(h_utc: pd.Timestamp):
        d0 = h_utc.date()
        h_in_day = h_utc.hour
        i0 = h_in_day * 12
        probs = _get_tree_raw(d0).probabilities

        scen_d = _get_corrected(d0)

        if h_in_day == 0:
            window_scen = scen_d
        else:
            d1 = d0 + timedelta(days=1)
            scen_d1 = _get_corrected(d1)
            window_scen = np.concatenate(
                [scen_d[:, :, i0:], scen_d1[:, :, :i0]], axis=2
            )

        stage1_scen = window_scen[:, :, :T1].transpose(0, 2, 1)   # [K, T1, 6]
        stage2_scen = window_scen[:, :, T1:].transpose(0, 2, 1)   # [K, T2, 6]
        stage1_mean = (probs[:, None, None] * stage1_scen).sum(axis=0)  # [T1, 6]

        return stage1_mean, stage2_scen, probs

    return get_stochastic_window


# ── Oracle verification ───────────────────────────────────────────────────────

def _verify_emax_oracle(rt_prices: pd.DataFrame, n_sample: int = 30) -> None:
    """Sample (product, hour) cells and verify E[max(s+δ, 0)] ≈ realized_mean."""
    print(f"\n--- E[max] Oracle Verification (n={n_sample} cells) ---")
    panel_days = [
        date(2026, 4, d) for d in range(20, 27)
    ] + [date(2026, 4, 27)]

    rng = random.Random(99)
    cells = []
    for _ in range(n_sample):
        d = rng.choice(panel_days)
        h = rng.randint(0, 23)
        p = rng.choice(_AS_IDX)
        cells.append((d, h, p))

    edge_log_v = {"near_zero": 0, "cap_hit": 0, "nonconv": 0}
    print(f"  {'Day':>12}  HoD  Prod    Target  Achieved   Error")
    max_err = 0.0
    for d, h, p in cells:
        tree   = _get_tree_raw(d)
        probs  = tree.probabilities
        scen   = tree.scenarios.copy()            # [K, 6, 288]
        rt_day = _rt_day_array(rt_prices, d)

        sl = slice(h * 12, (h + 1) * 12)
        s  = scen[:, p, sl]                       # [K, 12]
        rt_mean = float(rt_day[sl, p].mean())

        if rt_mean < _NEAR_ZERO:
            achieved = 0.0
            err = abs(achieved - rt_mean)
        else:
            delta, _, _ = _find_emax_delta(s, probs, rt_mean)
            achieved = _emax_target(s, probs, delta)
            err = abs(achieved - rt_mean)

        max_err = max(max_err, err)
        status = "OK" if err < _BISECT_TOL * 10 else "FAIL"
        pname = _AS_NAMES[p - 1]
        print(f"  {str(d):>12}  {h:>3}  {pname:<6}  {rt_mean:>7.3f}  {achieved:>8.3f}  {err:>7.4f}  {status}")

    print(f"  Max error across sample: {max_err:.5f} $/MWh  (tol={_BISECT_TOL})")
    if max_err > _BISECT_TOL * 10:
        raise RuntimeError(f"E[max] oracle verification FAILED: max_err={max_err:.5f}")
    print("  Verification PASSED.\n")


# ── Rolling stochastic LP with oracle scenarios ───────────────────────────────

def run_oracle_stochastic(
    rt_prices: pd.DataFrame,
    fix_lmp: bool,
    fix_as: bool,
    label: str,
) -> tuple[dict, dict]:
    """Run stochastic LP rolling backtest with oracle-corrected scenarios.

    Returns (result_dict, edge_log).
    """
    print(f"\n=== {label} ===")
    edge_log = {"near_zero": 0, "cap_hit": 0, "nonconv": 0}
    get_win  = _make_get_stochastic_window(rt_prices, fix_lmp, fix_as, edge_log)

    def get_lookahead(h_utc: pd.Timestamp) -> dict:
        stage1_mean, stage2_scen, probs = get_win(h_utc)
        return {
            "stage1_mean": stage1_mean,
            "stage2_scen": stage2_scen,
            "probs":       probs,
            "_hour_utc":   h_utc,
        }

    def solve_hour(lookahead: dict, s_init: float):
        d1, c1, a_ru1, a_rd1, a_rrs1, a_ecrs1, a_ns1, s1_end, _, solve_time = (
            solve_stochastic_hour(
                lookahead["stage1_mean"],
                lookahead["stage2_scen"],
                lookahead["probs"],
                BESS, s_init,
            )
        )
        h_utc = lookahead["_hour_utc"]
        idx = pd.date_range(h_utc, periods=T1, freq="5min")
        dispatch = pd.DataFrame({
            "discharge_mw":   d1,
            "charge_mw":      c1,
            "award_regup_mw": a_ru1,
            "award_regdn_mw": a_rd1,
            "award_rrs_mw":   a_rrs1,
            "award_ecrs_mw":  a_ecrs1,
            "award_nspin_mw": a_ns1,
        }, index=idx)
        dispatch.index.name = "timestamp_utc"
        return dispatch, s1_end, solve_time

    result = run_rolling_lp(
        bess=BESS,
        rt_prices=rt_prices,
        get_lookahead_fn=get_lookahead,
        solve_hour_fn=solve_hour,
        panel_start=PANEL_START,
        panel_end=PANEL_END,
    )

    total_cells = len([d for d in [date(2026,4,d) for d in range(20,27)] + [date(2026,4,27)]]) * 24 * 5
    near_zero_pct = 100.0 * edge_log["near_zero"] / max(total_cells, 1)
    cap_hit_pct   = 100.0 * edge_log["cap_hit"]   / max(total_cells, 1)

    print(f"  Energy revenue: ${result.revenue_energy:,.0f}")
    print(f"  AS revenue:     ${result.revenue_as:,.0f}")
    print(f"  Liquidation:    ${result.liquidation_revenue:,.0f}")
    print(f"  Total revenue:  ${result.revenue_total:,.0f}")
    print(f"  Wall clock:     {result.wall_clock_s:.1f}s ({len(result.hours)} hours)")
    print(f"  E[max] edge cases — near_zero: {edge_log['near_zero']} ({near_zero_pct:.1f}%)  "
          f"cap_hit: {edge_log['cap_hit']}  nonconv: {edge_log['nonconv']}")

    if edge_log["cap_hit"] / max(total_cells, 1) > 0.01:
        raise RuntimeError(
            f"δ cap hit in {edge_log['cap_hit']} cells ({cap_hit_pct:.1f}%) — exceeds 1% threshold. STOP."
        )

    return {
        "label":               label,
        "fix_lmp":             fix_lmp,
        "fix_as":              fix_as,
        "revenue_total":       result.revenue_total,
        "revenue_energy":      result.revenue_energy,
        "revenue_as":          result.revenue_as,
        "liquidation_revenue": result.liquidation_revenue,
        "wall_clock_s":        result.wall_clock_s,
    }, edge_log


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    wall_start = time.perf_counter()
    print("Loading RT prices...")
    rt = load_rt_prices()

    # ── Step 1 verification ───────────────────────────────────────────────────
    _verify_emax_oracle(rt, n_sample=30)

    # ── Step 2: re-run CF-B and CF-AB with E[max] oracle ─────────────────────
    cf_b,  edge_b  = run_oracle_stochastic(rt, fix_lmp=False, fix_as=True,  label="CF-B (E[max] AS oracle)")
    cf_ab, edge_ab = run_oracle_stochastic(rt, fix_lmp=True,  fix_as=True,  label="CF-AB (LMP + E[max] AS oracle)")

    # ── Attribution table (frozen legs reused) ────────────────────────────────
    baseline = _BASELINE_REVENUE
    delta_lmp   = _DELTA_LMP                                          # $21,478.96
    delta_as    = cf_b["revenue_total"]  - baseline
    interaction = cf_ab["revenue_total"] - baseline - delta_lmp - delta_as
    residual    = _PF_REVENUE - cf_ab["revenue_total"]
    identity    = delta_lmp + delta_as + interaction + residual
    stoch_to_pf = _PF_REVENUE - baseline                             # $113,235.73

    print("\n=== W4-A Attribution Table (E[max] CF-B) ===")
    print(f"Baseline (Stochastic):        ${baseline:>10,.2f}  [frozen]")
    print(f"CF-A (Oracle LMP):            ${_CFA_REVENUE:>10,.2f}  [frozen]")
    print(f"CF-B (E[max] AS oracle):      ${cf_b['revenue_total']:>10,.2f}")
    print(f"CF-AB (LMP + E[max] AS):      ${cf_ab['revenue_total']:>10,.2f}")
    print(f"PF LP (upper bound):          ${_PF_REVENUE:>10,.2f}  [reference]")
    print()
    print(f"Stochastic→PF headroom:       ${stoch_to_pf:>+10,.2f}")
    print()
    print(f"  ΔLMP        = {delta_lmp:>+12,.2f}  ({100*delta_lmp/stoch_to_pf:.1f}% of headroom)")
    print(f"  ΔAS         = {delta_as:>+12,.2f}  ({100*delta_as/stoch_to_pf:.1f}% of headroom)")
    print(f"  Interaction = {interaction:>+12,.2f}  ({100*interaction/stoch_to_pf:.1f}% of headroom)")
    print(f"  Residual    = {residual:>+12,.2f}  ({100*residual/stoch_to_pf:.1f}% of headroom)")
    print(f"  Identity:   {identity:>+12,.2f}  (should be {stoch_to_pf:,.2f})")
    print()
    print(f"E[max] edge cases:")
    print(f"  CF-B  — near_zero: {edge_b['near_zero']}, cap_hit: {edge_b['cap_hit']}, nonconv: {edge_b['nonconv']}")
    print(f"  CF-AB — near_zero: {edge_ab['near_zero']}, cap_hit: {edge_ab['cap_hit']}, nonconv: {edge_ab['nonconv']}")
    print(f"\nTotal wall clock: {time.perf_counter()-wall_start:.1f}s")

    # ── Persist ───────────────────────────────────────────────────────────────
    audit = {
        "panel_start":        str(PANEL_START),
        "panel_end":          str(PANEL_END),
        "canonical_seed":     CANONICAL_SEED,
        "baseline_revenue":   baseline,
        "cfa_revenue":        _CFA_REVENUE,
        "pf_revenue":         _PF_REVENUE,
        "cfb_emax":           cf_b,
        "cfab_emax":          cf_ab,
        "edge_log_cfb":       edge_b,
        "edge_log_cfab":      edge_ab,
        "attribution": {
            "stoch_to_pf":   stoch_to_pf,
            "delta_lmp":     delta_lmp,
            "delta_as":      delta_as,
            "interaction":   interaction,
            "residual":      residual,
            "identity_check": identity,
        },
    }
    out = AUDIT_DIR / "backtest_w4a.json"
    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
