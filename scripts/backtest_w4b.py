"""W4-B: Residual decomposition — formulation gap + dispersion calibration oracles.

Decomposes the $57,558 CF-AB→PF residual (the unexplained 50.8% of the
Stochastic→PF headroom left after W4-A's effective-price oracles) into:

  G          : formulation gap (structural / rolling-horizon, unfixable by forecast)
  ΔLMPdisp   : revenue gain from calibrating LMP scenario dispersion (lower bound)
  ΔASdisp    : revenue gain from calibrating AS  scenario dispersion (lower bound)
  remainder  : beyond-calibration misspecification + finite-K sampling

Run:  python scripts/backtest_w4b.py --phase {0,1,2,all}   (results → ADR 0011)

  Phase 0 (HARD GATE): 0.1 reproduce CF-AB ($294,054, expect exact); 0.2 formulation
    probe = stochastic LP with ALL K scenarios = realized RT path → R_struct, clamped
    at PANEL_END (canonical) to avoid the boundary-lookahead artifact.  G = PF −
    R_struct_clamped = +$14 (designated; bracket [$14, $4,467]).  Structural cost ≈ 0.

  Phase 1: dispersion calibration oracles on top of CF-AB.  LMP global scale → 80%
    central coverage (s=0.465; LMP is OVER-dispersed post-centering).  AS per-product
    scale + E[max] δ re-solve → BEST-ACHIEVABLE coverage (80% unreachable under E[max]
    + non-negativity; coverage peaks below target for all products).

  Phase 2: calibrated 2×2 (+LMPdisp/+ASdisp/+Both) + perfect-path upper bounds
    (U_LMP/U_AS).  Identity ΔLMPdisp+ΔASdisp+interaction+remainder = $57,558; bracket
    [calibration lower, perfect-path upper] per leg.  Remainder ≈ all LMP point error.

Reuses W4-A oracle machinery (CF-AB reproduction, E[max] bisection) from backtest_w4a.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

# W4-A machinery (module-level _dataset / _fc build the bootstrap forecaster on import)
from backtest_w4a import (  # noqa: E402
    _AS_IDX,
    _AS_NAMES,
    _NEAR_ZERO,
    _PRICE_COLS,
    BESS,
    PANEL_END,
    PANEL_START,
    _emax_target,
    _find_emax_delta,
    _get_tree_raw,
    _rt_day_array,
    load_rt_prices,
    run_oracle_stochastic,
)

from ercot_rtcb_bench.methods.rolling_lp import T1, T2, run_rolling_lp  # noqa: E402
from ercot_rtcb_bench.methods.stochastic_lp import solve_stochastic_hour  # noqa: E402

AUDIT_DIR = Path(__file__).parent.parent / "data" / "audit"

# ── Frozen reference numbers (from W4-A audit / ADR 0010 / W3-D PF breakdown) ──
_PF_REVENUE     = 351_612.00
_PF_ENERGY      = 253_765.00     # PF energy component (results_w3d.md)
_PF_AS          = 97_601.00      # PF AS component
_PF_LIQ         = 245.00         # PF terminal liquidation
_CFAB_EXPECTED  = 294_054.36     # CF-AB reproduction target
_RESIDUAL       = 57_557.64      # CF-AB → PF residual being decomposed
_REPRO_TOL      = 1.00           # $ tolerance for CF-AB reproduction (expect exact)
_G_VICINITY     = 4_467.00       # expected canonical-G neighbourhood (in-panel gap)
_G_DIVERGE_TOL  = 5_000.00       # |G_canonical − vicinity| beyond this → STOP (boundary-artifact scale)


# ── Formulation probe: stochastic LP with all K scenarios = realized RT path ───

def _make_get_realized_window(rt_prices: pd.DataFrame, clamp_panel_end: bool):
    """Factory: get_stochastic_window where every scenario IS the realized path.

    Zero dispersion, perfect center.  Stage-1 mean and every stage-2 scenario
    equal the realized RT price path over the lookahead window starting at h_utc.
    K and probs are taken from the real bootstrap tree so the LP configuration is
    identical to the baseline — only the price content changes.

    clamp_panel_end: if True, truncate the window at PANEL_END so NO post-panel
      intervals enter the objective (canonical probe — eliminates the
      boundary-lookahead / terminal-liquidation artifact that lets an unclamped
      rolling LP carry SoC past the panel edge and out-bank PF).  The final panel
      hour clamps to its committed hour only (T2=0; handled by the LP's empty-
      horizon guard → zero terminal value → battery drains, matching PF).
      If False, the standard full 24h window (may peek past PANEL_END).
    """
    full_len = T1 + T2  # 288 intervals = 24h

    def get_stochastic_window(h_utc: pd.Timestamp):
        probs = _get_tree_raw(h_utc.date()).probabilities          # [K]
        K = probs.shape[0]
        if clamp_panel_end:
            n_avail = int((PANEL_END - h_utc) / pd.Timedelta("5min"))
            window_len = min(full_len, n_avail)                    # committed hour always in-panel
        else:
            window_len = full_len
        idx = pd.date_range(h_utc, periods=window_len, freq="5min")
        path = rt_prices.reindex(idx, method="nearest")[_PRICE_COLS].to_numpy(dtype=np.float64)
        t2_eff = window_len - T1                                    # ≥ 0
        stage1_mean = path[:T1].copy()                             # [T1, 6]
        stage2_single = path[T1:T1 + t2_eff]                       # [t2_eff, 6]
        stage2_scen = np.repeat(stage2_single[None, :, :], K, axis=0)  # [K, t2_eff, 6]
        return stage1_mean, stage2_scen, probs

    return get_stochastic_window


def run_realized_path_stochastic(
    rt_prices: pd.DataFrame, label: str, clamp_panel_end: bool
) -> dict:
    """Rolling stochastic LP fed the realized path as every scenario → R_struct."""
    print(f"\n=== {label} ===")
    get_win = _make_get_realized_window(rt_prices, clamp_panel_end=clamp_panel_end)

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

    print(f"  Energy revenue: ${result.revenue_energy:,.0f}")
    print(f"  AS revenue:     ${result.revenue_as:,.0f}")
    print(f"  Liquidation:    ${result.liquidation_revenue:,.0f}")
    print(f"  Total revenue:  ${result.revenue_total:,.2f}")
    print(f"  Wall clock:     {result.wall_clock_s:.1f}s ({len(result.hours)} hours)")

    return {
        "label":               label,
        "revenue_total":       result.revenue_total,
        "revenue_energy":      result.revenue_energy,
        "revenue_as":          result.revenue_as,
        "liquidation_revenue": result.liquidation_revenue,
        "wall_clock_s":        result.wall_clock_s,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Dispersion calibration oracles (on top of CF-AB)
# ══════════════════════════════════════════════════════════════════════════════
#
# W3-B found AS prediction intervals cover realized only 51–56% vs an 80% target
# (under-dispersed scenarios).  Phase 1 measures how much that under-dispersion
# costs, by CALIBRATING scenario spread to 80% central-interval coverage and
# re-running the LP.  These are *calibration oracles* — lower bounds on the
# achievable gain (they fix only the second moment, not the shape).
#
# Mean-preserving scale around the per-interval probability-weighted mean:
#     s_k(t) → m(t) + scale·(s_k(t) − m(t)),   m(t) = Σ_k p_k s_k(t)
# This widens cross-scenario spread while leaving every per-interval mean (hence
# CF-A's per-hour LMP centering) exactly unchanged.
#
#   LMP: a single GLOBAL scale s, applied on top of CF-A centering.  No E[max].
#   AS : a per-product scale s_p, applied on top of the raw scenarios, then the
#        E[max] δ is RE-SOLVED per (p,h) so the effective price stays = realized.
#        Scaling changes E[max(·,0)] (convex), so δ must move with s_p — outer
#        bisection on s_p (coverage) wraps the inner E[max] bisection on δ.
#
# Coverage is measured on the FINAL scenarios the LP sees (post-scale, post-δ),
# pooled panel-wide over Apr 20–26.  near_zero AS cells (realized < $0.01, no
# dispersion possible) are excluded from the AS coverage target.

_PANEL_DAYS = [date(2026, 4, d) for d in range(20, 27)]   # Apr 20–26 (7 days)
_COVERAGE_TARGET = 0.80
_COVERAGE_GATE   = 0.03   # ±3 points tolerance at q=0.8 (Phase 1.3 gate)
_COVERAGE_QS     = (0.5, 0.8, 0.9)


def _panel_cache(rt_prices: pd.DataFrame) -> dict:
    """Build {day: (scenarios[K,6,288], probs[K], rt_day[288,6])} for the panel."""
    cache = {}
    for d in _PANEL_DAYS:
        tree = _get_tree_raw(d)
        cache[d] = (
            tree.scenarios.copy(),
            tree.probabilities,
            _rt_day_array(rt_prices, d),
        )
    return cache


def _weighted_quantile(V: np.ndarray, w: np.ndarray, q: float) -> np.ndarray:
    """Weighted quantile per column.  V:[K,N], w:[K] (sum 1), q scalar → [N]."""
    order = np.argsort(V, axis=0)
    Vs = np.take_along_axis(V, order, axis=0)
    ws = w[order]
    pos = np.cumsum(ws, axis=0) - 0.5 * ws          # Hazen plotting positions
    N = V.shape[1]
    out = np.empty(N)
    for n in range(N):
        out[n] = np.interp(q, pos[:, n], Vs[:, n])
    return out


def _central_interval_coverage(V: np.ndarray, w: np.ndarray, realized: np.ndarray, q: float) -> np.ndarray:
    """Bool [N]: realized inside the central-q interval [q_lo, q_hi] of V per column."""
    lo = _weighted_quantile(V, w, (1.0 - q) / 2.0)
    hi = _weighted_quantile(V, w, (1.0 + q) / 2.0)
    return (realized >= lo) & (realized <= hi)


def _lmp_scaled_day(scen: np.ndarray, probs: np.ndarray, rt_day: np.ndarray, scale: float) -> np.ndarray:
    """CF-A center + global dispersion scale on LMP for one day → [K,288]."""
    out = np.empty((scen.shape[0], 288))
    for h in range(24):
        sl = slice(h * 12, (h + 1) * 12)
        s = scen[:, 0, sl]
        fc_mean = float(probs @ s.mean(axis=1))
        rt_mean = float(rt_day[sl, 0].mean())
        centered = s + (rt_mean - fc_mean)                 # CF-A
        m_t = probs @ centered                             # [12] per-interval mean
        out[:, sl] = m_t[None, :] + scale * (centered - m_t[None, :])
    return out


def _lmp_coverage(cache: dict, scale: float, q: float) -> float:
    inside = []
    for d in _PANEL_DAYS:
        scen, probs, rt_day = cache[d]
        V = _lmp_scaled_day(scen, probs, rt_day, scale)
        inside.append(_central_interval_coverage(V, probs, rt_day[:, 0], q))
    return float(np.concatenate(inside).mean())


def _as_coverage(cache: dict, p: int, scale: float, q: float, edge_log: dict | None = None) -> float:
    """AS product-p coverage: scale around mean, re-solve E[max] δ, exclude near_zero."""
    inside = []
    for d in _PANEL_DAYS:
        scen, probs, rt_day = cache[d]
        for h in range(24):
            sl = slice(h * 12, (h + 1) * 12)
            rt_mean = float(rt_day[sl, p].mean())
            if rt_mean < _NEAR_ZERO:
                if edge_log is not None:
                    edge_log["near_zero"] += 1
                continue
            sp = scen[:, p, sl]
            m_t = probs @ sp
            scaled = m_t[None, :] + scale * (sp - m_t[None, :])
            delta, converged, reason = _find_emax_delta(scaled, probs, rt_mean)
            if edge_log is not None:
                if reason == "cap_hit":
                    edge_log["cap_hit"] += 1
                if not converged:
                    edge_log["nonconv"] += 1
            final = scaled + delta
            inside.append(_central_interval_coverage(final, probs, rt_day[sl, p], q))
    return float(np.concatenate(inside).mean())


def _bisect_scale(cov_fn, target: float, lo: float = 0.1, hi: float = 30.0,
                  tol: float = 0.003, max_iter: int = 40) -> tuple[float, float, str]:
    """Find scale s.t. cov_fn(scale) = target.  Coverage is monotone ↑ in scale.

    Returns (scale, coverage_at_scale, reason ∈ {'ok','floor','ceil'}).
    'floor': already ≥ target at min scale (over-dispersed); 'ceil': unreachable.
    Used for LMP (monotone).  AS coverage is NON-monotone (peaks below target) →
    use _maximize_coverage_scale instead.
    """
    c_lo = cov_fn(lo)
    if c_lo >= target:
        return lo, c_lo, "floor"
    c_hi = cov_fn(hi)
    if c_hi <= target:
        return hi, c_hi, "ceil"
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        c = cov_fn(mid)
        if abs(c - target) < tol:
            return mid, c, "ok"
        if c < target:
            lo = mid
        else:
            hi = mid
    mid = 0.5 * (lo + hi)
    return mid, cov_fn(mid), "ok"


def _maximize_coverage_scale(cov_fn) -> tuple[float, float]:
    """Find the coverage-MAXIMIZING scale (curve peak) — for AS, where 80% is
    unreachable.  Coarse grid + local refine.  Returns (scale, coverage_at_peak)."""
    coarse = [0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.3, 1.7, 2.2]
    pts = [(s, cov_fn(s)) for s in coarse]
    s_best, _ = max(pts, key=lambda x: x[1])
    fine = [round(s_best + k * 0.05, 4) for k in range(-3, 4) if s_best + k * 0.05 > 0.02]
    pts += [(s, cov_fn(s)) for s in fine]
    s_best, c_best = max(pts, key=lambda x: x[1])
    return s_best, c_best


def run_phase1(rt: pd.DataFrame) -> dict:
    """Calibrate LMP global scale and AS per-product scales to 80% coverage."""
    print("\n" + "=" * 70)
    print("PHASE 1 — Dispersion calibration oracles (on top of CF-AB)")
    print("=" * 70)
    cache = _panel_cache(rt)

    # ── 1.1 LMP global scale ──────────────────────────────────────────────────
    print("\n--- 1.1 LMP global dispersion scale ---")
    base_lmp = {q: _lmp_coverage(cache, 1.0, q) for q in _COVERAGE_QS}
    print(f"  Baseline (scale=1.0) coverage: "
          f"q50={base_lmp[0.5]:.3f}  q80={base_lmp[0.8]:.3f}  q90={base_lmp[0.9]:.3f}")
    s_lmp, cov_lmp_08, reason_lmp = _bisect_scale(
        lambda s: _lmp_coverage(cache, s, 0.8), _COVERAGE_TARGET
    )
    cal_lmp = {q: _lmp_coverage(cache, s_lmp, q) for q in _COVERAGE_QS}
    print(f"  Calibrated scale s_lmp = {s_lmp:.4f}  ({reason_lmp})")
    print(f"  Calibrated coverage:           "
          f"q50={cal_lmp[0.5]:.3f}  q80={cal_lmp[0.8]:.3f}  q90={cal_lmp[0.9]:.3f}")

    # ── 1.2 AS per-product scales — BEST-ACHIEVABLE (argmax coverage) ──────────
    # 80% central coverage is UNREACHABLE under E[max] + non-negativity (coverage
    # peaks below target for all products).  We instead pick each product's
    # coverage-maximizing scale → ΔASdisp is a calibration LOWER BOUND, and the
    # finding is the sub-80% coverage ceiling itself (ADR 0011).
    print("\n--- 1.2 AS per-product dispersion scales (BEST-ACHIEVABLE, argmax cov) ---")
    print("  (80% unreachable under E[max]+non-negativity — reporting coverage ceiling)")
    as_scales = []
    as_cov = {}
    as_base = {}
    edge_log = {"near_zero": 0, "cap_hit": 0, "nonconv": 0}
    for j, p in enumerate(_AS_IDX):
        name = _AS_NAMES[j]
        base = {q: _as_coverage(cache, p, 1.0, q) for q in _COVERAGE_QS}
        s_p, _peak = _maximize_coverage_scale(lambda s, p=p: _as_coverage(cache, p, s, 0.8))
        cal = {q: _as_coverage(cache, p, s_p, q, edge_log) for q in _COVERAGE_QS}
        as_scales.append(s_p)
        as_base[name] = base
        as_cov[name] = cal
        print(f"  {name:<6}: base q80={base[0.8]:.3f}  →  s_p*={s_p:7.4f}  "
              f"PEAK q50={cal[0.5]:.3f} q80={cal[0.8]:.3f} q90={cal[0.9]:.3f}  "
              f"(ceiling {cal[0.8]:.3f} < 0.80)")
    print(f"  E[max] edge cases (per coverage pass): "
          f"near_zero≈{edge_log['near_zero']//3}  cap_hit={edge_log['cap_hit']}  "
          f"nonconv={edge_log['nonconv']}")

    # ── 1.3 Verification gate ─────────────────────────────────────────────────
    # LMP MUST hit 80% ±3pts (monotone, reachable).  AS is reported as a ceiling
    # (80% proven unreachable) — informational, not a pass/fail bar.
    print("\n--- 1.3 Verification gate ---")
    lmp_err = abs(cal_lmp[0.8] - _COVERAGE_TARGET)
    lmp_ok = lmp_err <= _COVERAGE_GATE
    print(f"  LMP (MUST hit 0.80±0.03): q80={cal_lmp[0.8]:.3f}  |err|={lmp_err:.3f}  "
          f"{'OK' if lmp_ok else 'FAIL'}")
    print("  AS  (coverage CEILING, 0.80 unreachable — informational):")
    for name in _AS_NAMES:
        print(f"    {name:<6}: ceiling q80={as_cov[name][0.8]:.3f}  (target 0.80 unreachable)")

    # E[max] cell verification (≥20 cells) on the AS-scaled scenarios
    _verify_emax_scaled(cache, as_scales, n_sample=30)

    if not lmp_ok:
        raise RuntimeError(
            f"Phase 1.3 LMP coverage gate FAILED: q80={cal_lmp[0.8]:.3f} "
            f"not within ±3 pts of 0.80. STOP."
        )
    print("  GATE 1.3 PASSED — LMP at 0.80±0.03; AS ceilings recorded.")

    return {
        "lmp_scale":      s_lmp,
        "lmp_reason":     reason_lmp,
        "as_scales":      {n: as_scales[j] for j, n in enumerate(_AS_NAMES)},
        "as_scales_list": as_scales,
        "coverage_target": _COVERAGE_TARGET,
        "lmp_coverage_base": base_lmp,
        "lmp_coverage_cal":  cal_lmp,
        "as_coverage_base":  as_base,
        "as_coverage_ceiling": as_cov,
        "as_coverage_unreachable": True,
    }


def _verify_emax_scaled(cache: dict, as_scales: list, n_sample: int = 30) -> None:
    """Verify E[max(scale·centered + δ, 0)] ≈ realized on sampled (p,h) cells."""
    import random
    print(f"  E[max] verification on {n_sample} scaled (p,h) cells:")
    rng = random.Random(123)
    max_err = 0.0
    n_checked = 0
    for _ in range(n_sample):
        d = rng.choice(_PANEL_DAYS)
        h = rng.randint(0, 23)
        j = rng.randint(0, len(_AS_IDX) - 1)
        p = _AS_IDX[j]
        scen, probs, rt_day = cache[d]
        sl = slice(h * 12, (h + 1) * 12)
        rt_mean = float(rt_day[sl, p].mean())
        if rt_mean < _NEAR_ZERO:
            continue
        sp = scen[:, p, sl]
        m_t = probs @ sp
        scaled = m_t[None, :] + as_scales[j] * (sp - m_t[None, :])
        delta, _, _ = _find_emax_delta(scaled, probs, rt_mean)
        achieved = _emax_target(scaled, probs, delta)
        max_err = max(max_err, abs(achieved - rt_mean))
        n_checked += 1
    print(f"    checked {n_checked} non-near-zero cells, max E[max] error {max_err:.5f} $/MWh")
    if n_checked < 20:
        raise RuntimeError(f"E[max] verification: only {n_checked} cells (<20). STOP.")
    if max_err > 0.01:
        raise RuntimeError(f"E[max] verification: max_err {max_err:.5f} > 0.01. STOP.")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Calibrated 2×2 + perfect-path upper bounds (standard harness)
# ══════════════════════════════════════════════════════════════════════════════
#
# All runs use the STANDARD (unclamped) rolling window — same convention as CF-AB
# ($294,054) — so they are directly comparable.  The dispersion-correction window
# generalises W4-A's CF-AB window with two extra knobs per leg:
#
#   lmp_mode ∈ {"cfa_scaled" (CF-A center + global scale), "realized" (perfect)}
#   as_mode  ∈ {"emax_scaled" (per-product scale + E[max] δ), "realized" (perfect)}
#
#   CF-AB        : cfa_scaled(1.0) + emax_scaled([1]*5)   → reproduces $294,054
#   +LMPdisp     : cfa_scaled(s_lmp) + emax_scaled([1]*5)
#   +ASdisp      : cfa_scaled(1.0) + emax_scaled(s_p*)
#   +Both        : cfa_scaled(s_lmp) + emax_scaled(s_p*)
#   U_LMP (upper): realized LMP + emax_scaled([1]*5)
#   U_AS  (upper): cfa_scaled(1.0) + realized AS
#   U_both       : realized LMP + realized AS ≡ unclamped R_struct ($353,017 check)
#
# Upper-bound (realized-path) legs inherit the boundary-lookahead artifact
# (≤ ~$1.4k, the unclamped vs clamped R_struct gap) — noted in ADR 0011.

def _correct_day_v2(
    scen: np.ndarray, probs: np.ndarray, rt_day: np.ndarray,
    lmp_mode: str, lmp_scale: float,
    as_mode: str, as_scales: list, edge_log: dict,
) -> np.ndarray:
    """Build a CF-AB + dispersion (or perfect-path) corrected day array [K,6,288]."""
    corrected = scen.copy()
    for h in range(24):
        sl = slice(h * 12, (h + 1) * 12)

        # ── LMP leg ───────────────────────────────────────────────────────────
        if lmp_mode == "realized":
            corrected[:, 0, sl] = rt_day[sl, 0][None, :]
        else:  # cfa_scaled
            s = corrected[:, 0, sl]
            fc_mean = float(probs @ s.mean(axis=1))
            rt_mean = float(rt_day[sl, 0].mean())
            centered = s + (rt_mean - fc_mean)
            m_t = probs @ centered
            corrected[:, 0, sl] = m_t[None, :] + lmp_scale * (centered - m_t[None, :])

        # ── AS legs ───────────────────────────────────────────────────────────
        for j, p in enumerate(_AS_IDX):
            if as_mode == "realized":
                corrected[:, p, sl] = rt_day[sl, p][None, :]
                continue
            rt_mean = float(rt_day[sl, p].mean())
            if rt_mean < _NEAR_ZERO:
                corrected[:, p, sl] = 0.0
                edge_log["near_zero"] += 1
                continue
            sp = corrected[:, p, sl]
            m_t = probs @ sp
            scaled = m_t[None, :] + as_scales[j] * (sp - m_t[None, :])
            delta, converged, reason = _find_emax_delta(scaled, probs, rt_mean)
            if reason == "cap_hit":
                edge_log["cap_hit"] += 1
            if not converged:
                edge_log["nonconv"] += 1
            corrected[:, p, sl] = scaled + delta
    return corrected


def _make_get_window_v2(rt_prices, lmp_mode, lmp_scale, as_mode, as_scales, edge_log):
    """Factory: standard (unclamped) rolling window over v2-corrected day arrays."""
    oracle_cache: dict[date, np.ndarray] = {}

    def _get_corrected(d: date) -> np.ndarray:
        if d not in oracle_cache:
            tree = _get_tree_raw(d)
            oracle_cache[d] = _correct_day_v2(
                tree.scenarios.copy(), tree.probabilities, _rt_day_array(rt_prices, d),
                lmp_mode, lmp_scale, as_mode, as_scales, edge_log,
            )
        return oracle_cache[d]

    def get_stochastic_window(h_utc: pd.Timestamp):
        d0 = h_utc.date()
        i0 = h_utc.hour * 12
        probs = _get_tree_raw(d0).probabilities
        scen_d = _get_corrected(d0)
        if h_utc.hour == 0:
            window_scen = scen_d
        else:
            scen_d1 = _get_corrected(d0 + timedelta(days=1))
            window_scen = np.concatenate([scen_d[:, :, i0:], scen_d1[:, :, :i0]], axis=2)
        stage1_scen = window_scen[:, :, :T1].transpose(0, 2, 1)   # [K, T1, 6]
        stage2_scen = window_scen[:, :, T1:].transpose(0, 2, 1)   # [K, T2, 6]
        stage1_mean = (probs[:, None, None] * stage1_scen).sum(axis=0)  # [T1, 6]
        return stage1_mean, stage2_scen, probs

    return get_stochastic_window


def run_dispersion_stochastic(rt_prices, lmp_mode, lmp_scale, as_mode, as_scales, label):
    """Rolling stochastic LP over v2-corrected scenarios.  Returns result dict."""
    print(f"\n=== {label} ===")
    edge_log = {"near_zero": 0, "cap_hit": 0, "nonconv": 0}
    get_win = _make_get_window_v2(rt_prices, lmp_mode, lmp_scale, as_mode, as_scales, edge_log)

    def get_lookahead(h_utc):
        stage1_mean, stage2_scen, probs = get_win(h_utc)
        return {"stage1_mean": stage1_mean, "stage2_scen": stage2_scen,
                "probs": probs, "_hour_utc": h_utc}

    def solve_hour(lookahead, s_init):
        d1, c1, a_ru1, a_rd1, a_rrs1, a_ecrs1, a_ns1, s1_end, _, solve_time = (
            solve_stochastic_hour(lookahead["stage1_mean"], lookahead["stage2_scen"],
                                  lookahead["probs"], BESS, s_init)
        )
        idx = pd.date_range(lookahead["_hour_utc"], periods=T1, freq="5min")
        dispatch = pd.DataFrame({
            "discharge_mw": d1, "charge_mw": c1, "award_regup_mw": a_ru1,
            "award_regdn_mw": a_rd1, "award_rrs_mw": a_rrs1,
            "award_ecrs_mw": a_ecrs1, "award_nspin_mw": a_ns1,
        }, index=idx)
        dispatch.index.name = "timestamp_utc"
        return dispatch, s1_end, solve_time

    result = run_rolling_lp(bess=BESS, rt_prices=rt_prices, get_lookahead_fn=get_lookahead,
                            solve_hour_fn=solve_hour, panel_start=PANEL_START, panel_end=PANEL_END)
    print(f"  Total revenue: ${result.revenue_total:,.2f}  "
          f"(E ${result.revenue_energy:,.0f} / AS ${result.revenue_as:,.0f} / "
          f"Liq ${result.liquidation_revenue:,.0f})  {result.wall_clock_s:.0f}s")
    return {
        "label": label, "revenue_total": result.revenue_total,
        "revenue_energy": result.revenue_energy, "revenue_as": result.revenue_as,
        "liquidation_revenue": result.liquidation_revenue, "edge_log": edge_log,
    }


def run_phase2(rt: pd.DataFrame, calib: dict) -> dict:
    """Calibrated 2×2 dispersion attribution + perfect-path upper-bound bracket."""
    print("\n" + "=" * 70)
    print("PHASE 2 — Calibrated dispersion 2×2 + perfect-path upper bounds")
    print("=" * 70)
    s_lmp = calib["lmp_scale"]
    s_as = [calib["as_scales"][n] for n in _AS_NAMES]
    ones = [1.0] * 5
    print(f"  Calibrated scales: LMP s={s_lmp:.4f}  AS s_p*={[round(x,3) for x in s_as]}")

    base = _CFAB_EXPECTED   # CF-AB frozen baseline ($294,054.36)

    # Regression: reproduce CF-AB through the v2 machinery (scales=1) — must match.
    cfab_v2 = run_dispersion_stochastic(rt, "cfa_scaled", 1.0, "emax_scaled", ones,
                                        "CF-AB regression (v2, scales=1)")
    drift = cfab_v2["revenue_total"] - _CFAB_EXPECTED
    print(f"  CF-AB v2 regression drift: ${drift:+,.2f}  (tol ±${_REPRO_TOL:.2f})")
    if abs(drift) > _REPRO_TOL:
        raise RuntimeError(f"CF-AB v2 regression FAILED: drift ${drift:+,.2f}. STOP.")

    # Calibrated 2×2
    r_lmp  = run_dispersion_stochastic(rt, "cfa_scaled", s_lmp, "emax_scaled", ones,
                                       "+LMPdisp (s_lmp)")
    r_as   = run_dispersion_stochastic(rt, "cfa_scaled", 1.0,   "emax_scaled", s_as,
                                       "+ASdisp (s_p*)")
    r_both = run_dispersion_stochastic(rt, "cfa_scaled", s_lmp, "emax_scaled", s_as,
                                       "+Both dispersion")

    # Perfect-path upper bounds (realized leg) — standard harness
    u_lmp  = run_dispersion_stochastic(rt, "realized", 1.0, "emax_scaled", ones,
                                       "U_LMP (realized LMP + E[max] AS)")
    u_as   = run_dispersion_stochastic(rt, "cfa_scaled", 1.0, "realized", ones,
                                       "U_AS (CF-A LMP + realized AS)")
    u_both = run_dispersion_stochastic(rt, "realized", 1.0, "realized", ones,
                                       "U_both (realized both ≡ unclamped R_struct)")

    # ── Decomposition (identity: ΔLMPdisp+ΔASdisp+interaction+remainder = residual)
    d_lmp = r_lmp["revenue_total"]  - base
    d_as  = r_as["revenue_total"]   - base
    inter = r_both["revenue_total"] - base - d_lmp - d_as
    remainder = _PF_REVENUE - r_both["revenue_total"]
    identity  = d_lmp + d_as + inter + remainder

    d_lmp_up = u_lmp["revenue_total"] - base
    d_as_up  = u_as["revenue_total"]  - base
    uboth_check = u_both["revenue_total"]   # ≈ $353,017 (unclamped R_struct)

    print("\n" + "=" * 70)
    print("PHASE 2 — Residual decomposition ($57,558 = PF − CF-AB)")
    print("=" * 70)
    print(f"  CF-AB baseline:               ${base:>11,.2f}")
    print(f"  +LMPdisp:                     ${r_lmp['revenue_total']:>11,.2f}  ΔLMPdisp = ${d_lmp:>+10,.2f}")
    print(f"  +ASdisp:                      ${r_as['revenue_total']:>11,.2f}  ΔASdisp  = ${d_as:>+10,.2f}")
    print(f"  +Both:                        ${r_both['revenue_total']:>11,.2f}  inter    = ${inter:>+10,.2f}")
    print(f"  PF:                           ${_PF_REVENUE:>11,.2f}  remainder= ${remainder:>+10,.2f}")
    print(f"  Identity ΔL+ΔA+int+rem:       ${identity:>+11,.2f}  (= residual ${_RESIDUAL:,.2f})")
    print()
    print("  Bracket [calibration lower bound, perfect-path upper bound]:")
    print(f"    LMP : [${d_lmp:>+10,.2f}, ${d_lmp_up:>+10,.2f}]")
    print(f"    AS  : [${d_as:>+10,.2f}, ${d_as_up:>+10,.2f}]")
    print(f"  U_both consistency: ${uboth_check:,.2f}  (expect ≈ $353,017 unclamped R_struct)")
    print()
    print("  Cross-checks:")
    print(f"    remainder ≳ G? remainder=${remainder:,.2f}  G=$14.08  "
          f"{'OK' if remainder >= 14.08 else 'FAIL'}")
    print(f"    K-probe trigger (PF − rev_Both > ~$17k)? remainder=${remainder:,.0f}  "
          f"{'FIRES → recommend K=50 in Phase 3' if remainder > 17_000 else 'no'}")

    return {
        "calibration": {"lmp_scale": s_lmp, "as_scales": dict(zip(_AS_NAMES, s_as, strict=True))},
        "cfab_v2_drift": drift,
        "runs": {
            "lmpdisp": r_lmp, "asdisp": r_as, "both": r_both,
            "u_lmp": u_lmp, "u_as": u_as, "u_both": u_both,
        },
        "decomposition": {
            "baseline_cfab": base,
            "delta_lmpdisp": d_lmp,
            "delta_asdisp": d_as,
            "interaction2": inter,
            "remainder": remainder,
            "identity_check": identity,
            "residual": _RESIDUAL,
        },
        "bracket": {
            "lmp": [d_lmp, d_lmp_up],
            "as":  [d_as, d_as_up],
        },
        "u_both_consistency": uboth_check,
        "remainder_ge_G": remainder >= 14.08,
        "kprobe_fires": remainder > 17_000,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 0 (wrapped) + MAIN dispatch
# ══════════════════════════════════════════════════════════════════════════════

def run_phase0(rt: pd.DataFrame) -> dict:
    # ── Phase 0.1: reproduce CF-AB ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PHASE 0.1 — Reproduce CF-AB (HARD GATE)")
    print("=" * 70)
    cfab, _edge = run_oracle_stochastic(
        rt, fix_lmp=True, fix_as=True, label="CF-AB reproduction (LMP + E[max] AS)"
    )
    cfab_rev = cfab["revenue_total"]
    drift = cfab_rev - _CFAB_EXPECTED
    print(f"\n  CF-AB reproduced: ${cfab_rev:,.2f}")
    print(f"  Expected:         ${_CFAB_EXPECTED:,.2f}")
    print(f"  Drift:            ${drift:+,.2f}  (tol ±${_REPRO_TOL:.2f})")
    if abs(drift) > _REPRO_TOL:
        raise RuntimeError(
            f"CF-AB reproduction FAILED: drift ${drift:+,.2f} exceeds ±${_REPRO_TOL:.2f}. STOP."
        )
    print("  GATE 0.1 PASSED — CF-AB reproduces.")

    # ── Phase 0.2: formulation probe (clamped = canonical, unclamped = artifact) ─
    print("\n" + "=" * 70)
    print("PHASE 0.2 — Formulation probe (realized path as every scenario)")
    print("=" * 70)
    print("Boundary convention: an UNCLAMPED 24h rolling window peeks past PANEL_END")
    print("and lets the LP bank post-panel SoC as terminal liquidation, out-banking")
    print("PF (G<0 artifact). The CANONICAL probe clamps each window at PANEL_END so")
    print("no post-panel interval enters the objective; the final hour clamps to its")
    print("committed hour (T2=0 → zero terminal value → drains, matching PF).")

    r_unclamped = run_realized_path_stochastic(
        rt, label="R_struct UNCLAMPED (24h window, peeks past panel — artifact)",
        clamp_panel_end=False,
    )
    r_clamped = run_realized_path_stochastic(
        rt, label="R_struct CLAMPED at PANEL_END (canonical)",
        clamp_panel_end=True,
    )

    r_struct = r_clamped["revenue_total"]
    G_canonical = _PF_REVENUE - r_struct
    pf_inpanel   = _PF_ENERGY + _PF_AS
    runc_inpanel = r_unclamped["revenue_energy"] + r_unclamped["revenue_as"]
    G_inpanel    = pf_inpanel - runc_inpanel

    print("\n" + "=" * 70)
    print("PHASE 0 GATE REPORT")
    print("=" * 70)
    print("  Component breakdown (Energy / AS / Liquidation / Total):")
    print(f"    PF                : ${_PF_ENERGY:>11,.0f} / ${_PF_AS:>10,.0f} / "
          f"${_PF_LIQ:>8,.0f} / ${_PF_REVENUE:>11,.2f}")
    print(f"    R_struct unclamped: ${r_unclamped['revenue_energy']:>11,.0f} / "
          f"${r_unclamped['revenue_as']:>10,.0f} / "
          f"${r_unclamped['liquidation_revenue']:>8,.0f} / "
          f"${r_unclamped['revenue_total']:>11,.2f}")
    print(f"    R_struct clamped  : ${r_clamped['revenue_energy']:>11,.0f} / "
          f"${r_clamped['revenue_as']:>10,.0f} / "
          f"${r_clamped['liquidation_revenue']:>8,.0f} / "
          f"${r_clamped['revenue_total']:>11,.2f}")
    print()
    print(f"  G_canonical = PF − R_struct_clamped   = ${G_canonical:>+12,.2f}")
    print(f"  G_inpanel   (Option-1 cross-check)    = ${G_inpanel:>+12,.2f}  "
          f"[energy+AS only, unclamped; no new run]")
    print(f"  Residual to decompose                 = ${_RESIDUAL:>12,.2f}")

    if G_canonical < 0:
        raise RuntimeError(
            f"Formulation probe STILL BROKEN: G_canonical = ${G_canonical:+,.2f} < 0 "
            f"even after clamping. STOP and report."
        )
    if abs(G_canonical - _G_VICINITY) > _G_DIVERGE_TOL:
        raise RuntimeError(
            f"G_canonical = ${G_canonical:+,.2f} diverges wildly from the in-panel "
            f"vicinity (${_G_VICINITY:,.0f} ± ${_G_DIVERGE_TOL:,.0f}). STOP and report."
        )
    print("  GATE 0.2 PASSED — G_canonical ≥ 0 (PF weakly dominates).")

    return {
        "cfab_reproduced":      cfab,
        "cfab_expected":        _CFAB_EXPECTED,
        "cfab_drift":           drift,
        "r_struct_clamped":     r_clamped,
        "r_struct_unclamped":   r_unclamped,
        "pf": {
            "revenue_total":  _PF_REVENUE,
            "revenue_energy": _PF_ENERGY,
            "revenue_as":     _PF_AS,
            "liquidation":    _PF_LIQ,
        },
        "G_canonical":           G_canonical,
        "G_inpanel_crosscheck":  G_inpanel,
        "residual":              _RESIDUAL,
        "boundary_artifact_liq": r_unclamped["liquidation_revenue"] - _PF_LIQ,
    }


def _merge_audit(block: dict) -> None:
    """Read-modify-write the W4-B audit json so phases accumulate."""
    out = AUDIT_DIR / "backtest_w4b.json"
    audit = {}
    if out.exists():
        audit = json.loads(out.read_text())
    audit.setdefault("panel_start", str(PANEL_START))
    audit.setdefault("panel_end", str(PANEL_END))
    audit.update(block)
    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"Wrote {out}")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["0", "1", "2", "all"], default="all")
    args = ap.parse_args()

    wall_start = time.perf_counter()
    print("Loading RT prices...")
    rt = load_rt_prices()

    if args.phase in ("0", "all"):
        _merge_audit({"phase0": run_phase0(rt)})
    if args.phase in ("1", "all"):
        _merge_audit({"phase1": run_phase1(rt)})
    if args.phase in ("2", "all"):
        out = AUDIT_DIR / "backtest_w4b.json"
        calib = json.loads(out.read_text())["phase1"] if out.exists() else None
        if calib is None or "lmp_scale" not in calib:
            raise RuntimeError("Phase 2 needs Phase 1 calibration — run --phase 1 first.")
        _merge_audit({"phase2": run_phase2(rt, calib)})

    print(f"\nTotal wall clock: {time.perf_counter()-wall_start:.1f}s")


if __name__ == "__main__":
    main()
