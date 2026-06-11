"""W5-A Phase 2+3: DAM AS anchor scarcity-shrinkage — fit, validate, eval.

Implements the locked decision: per-product two-regime multiplicative shrinkage of
the DAM AS anchor, conditioned ONLY on the DAM AS quote level (ex-ante). Products
{regup, rrs, ecrs, nspin}; RegDn and LMP untouched. Single parameter s_p per product
(τ_p = train q90, fixed). Baseline remains runnable with correction disabled.

Phase 2: τ_p = q90(train DAM quote); fit s_p by method-of-moments (drive the
  high-regime E[max] effective bias to ~0) on a faithful analog-level reconstruction
  of the bootstrap; verify on train through the real (k-medoids) forecaster; val
  mid-gate (directional improvement + low-regime no-harm).
Phase 3: rolling Stochastic LP on the locked eval panel (Apr 20–26) with the
  corrected anchor → ΔW5A, recovery fraction of the $36,393 oracle bound, component
  and per-day breakdown, PF sanity.

Windows: train Jan 23–Apr 13 · val Apr 14–19 · eval Apr 20–26 (locked).
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

from ercot_rtcb_bench.forecaster import ASAnchorCorrection, BootstrapForecaster, ForecasterDataset
from ercot_rtcb_bench.forecaster.analog import match_analogs
from ercot_rtcb_bench.forecaster.bootstrap import _impute_series, _impute_zero
from ercot_rtcb_bench.forecaster.forecaster import CANONICAL_SEED, RECENCY_HALF_LIFE
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.rolling_lp import T1, run_rolling_lp
from ercot_rtcb_bench.methods.stochastic_lp import solve_stochastic_hour

AUDIT_DIR = Path(__file__).parent.parent / "data" / "audit"
DATA_DIR  = Path(__file__).parent.parent / "data" / "processed" / "forecaster"
BESS      = BESSParams.default_100mw_4hr()

PANEL_START = pd.Timestamp("2026-04-20 00:00", tz="UTC")
PANEL_END   = pd.Timestamp("2026-04-27 00:00", tz="UTC")

_PRODUCTS = ["regup", "rrs", "ecrs", "nspin"]          # RegDn excluded (flat bias ≈ 0)
_NAME_IDX = {"regup": 1, "regdn": 2, "rrs": 3, "ecrs": 4, "nspin": 5}

_TRAIN_START = date(2026, 1, 23)
_TRAIN_END   = date(2026, 4, 14)   # exclusive → through Apr 13
_VAL_START   = date(2026, 4, 14)
_VAL_END     = date(2026, 4, 20)   # exclusive → Apr 14–19

_BASELINE = 238_376.27
_ORACLE_BOUND = 36_393.0           # W4-A ΔAS oracle bound
_PF = 351_612.00
_REPRO_TOL = 1.00
_FIT_TOL = 1e-4

_dataset = ForecasterDataset()


# ── Data ────────────────────────────────────────────────────────────────────────

def load_rt_prices() -> pd.DataFrame:
    parts = []
    for m in ["2026-04", "2026-05"]:
        df = pd.read_parquet(DATA_DIR / "rt_prices" / f"{m}.parquet").set_index("timestamp_utc")
        parts.append(df)
    return pd.concat(parts).sort_index().ffill().bfill()


def _days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d < end:
        out.append(d)
        d += timedelta(days=1)
    return out


# ── Phase 2: analog-level reconstruction (faithful pre-reduction bootstrap) ──────

def _reconstruct_day(d: date) -> tuple | None:
    """Replicate bootstrap inputs for *d*: (dam_target[6,288], R[N,6,288],
    recency w[N], realized[6,288]).  Same coverage filter / imputation as bootstrap."""
    analog_days, _dist, _info = match_analogs(d, _dataset, n=40)
    resids, used = [], []
    for a in analog_days:
        rt_a = _dataset.get_rt_array(a)
        dam_a = _dataset.get_dam_array(a)
        if np.isfinite(rt_a).mean() < 0.90 or np.isfinite(dam_a).mean() < 0.90:
            continue
        resids.append(_impute_series(rt_a) - _impute_zero(dam_a))
        used.append(a)
    if not resids:
        return None
    R = np.stack(resids).astype(np.float64)                 # [N,6,288] (f64: avoid BLAS f32 FP-flag noise)
    ord_t = d.toordinal()
    raw = np.array([np.exp(-(ord_t - a.toordinal()) / RECENCY_HALF_LIFE) for a in used])
    w = (raw / raw.sum()).astype(np.float64)                # [N]
    dam_t = _impute_zero(_dataset.get_dam_array(d))         # [6,288]
    rt_t = _dataset.get_rt_array(d)                         # [6,288] realized
    return dam_t, R, w, rt_t


def _build_proxy_cache(train_days: list[date]) -> tuple[dict, list[date]]:
    cache, used = {}, []
    for d in train_days:
        rec = _reconstruct_day(d)
        if rec is None:
            continue
        cache[d] = rec
        used.append(d)
    return cache, used


def _train_quote_q90(cache: dict, used: list[date]) -> dict:
    """τ_p = q90 of train DAM AS quotes (5-min ffilled). Also report hourly q90."""
    tau, tau_hourly = {}, {}
    for name in _PRODUCTS:
        p = _NAME_IDX[name]
        fivemin = np.concatenate([cache[d][0][p] for d in used])           # [days*288]
        hourly  = np.concatenate([cache[d][0][p][::12] for d in used])     # one per hour
        tau[name] = float(np.quantile(fivemin, 0.90))
        tau_hourly[name] = float(np.quantile(hourly, 0.90))
    return tau, tau_hourly


def _proxy_high_bias(cache: dict, used: list[date], name: str, tau_p: float, s: float) -> tuple[float, int]:
    """Mean high-regime (quote>τ) effective bias = E_a[max(corr_anchor+resid,0)] − realized."""
    p = _NAME_IDX[name]
    num, cnt = 0.0, 0
    for d in used:
        dam_t, R, w, rt_t = cache[d]
        anchor = dam_t[p]                                   # [288]
        hi = anchor > tau_p
        if not hi.any():
            continue
        corr = np.where(hi, tau_p + s * (anchor - tau_p), anchor)        # [288]
        scen = np.maximum(corr[None, :] + R[:, p, :], 0.0)              # [N,288]
        # broadcast-sum (not w @ scen): avoids the BLAS matmul kernel's spurious
        # divide/overflow FP-flag warnings on macOS Accelerate (result identical).
        feff = (w[:, None] * scen).sum(axis=0)                          # [288]
        num += float((feff[hi] - rt_t[p, hi]).sum())
        cnt += int(hi.sum())
    return (num / cnt if cnt else float("nan")), cnt


def _fit_s(cache: dict, used: list[date], name: str, tau_p: float) -> tuple[float, str, float, int]:
    b0, n_hi = _proxy_high_bias(cache, used, name, tau_p, 0.0)
    b1, _ = _proxy_high_bias(cache, used, name, tau_p, 1.0)
    if b1 <= 0:
        return 1.0, "no_corr_needed", b1, n_hi          # uncorrected not over (unexpected)
    if b0 >= 0:
        return 0.0, "clamped_zero", b0, n_hi            # even τ-pin still over-forecasts
    lo, hi = 0.0, 1.0                                    # bias monotone ↑ in s; b0<0<b1
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        bm, _ = _proxy_high_bias(cache, used, name, tau_p, mid)
        if abs(bm) < _FIT_TOL:
            return mid, "ok", bm, n_hi
        if bm < 0:
            lo = mid
        else:
            hi = mid
    mid = 0.5 * (lo + hi)
    bm, _ = _proxy_high_bias(cache, used, name, tau_p, mid)
    return mid, "ok", bm, n_hi


# ── Real-forecaster effective bias (train-verify / val) ──────────────────────────

def _effective_bias_through_forecaster(fc: BootstrapForecaster, days: list[date], tau: dict) -> dict:
    """Per product: high/low-regime mean effective (E[max]) bias through the real
    (k-medoids) forecaster. Regime split on the RAW DAM quote (tree.point_forecast)."""
    acc = {n: {"hi_num": 0.0, "hi_cnt": 0, "lo_num": 0.0, "lo_cnt": 0} for n in _PRODUCTS}
    for d in days:
        try:
            tree = fc.forecast(d)
        except Exception:  # noqa: BLE001
            continue
        eff = np.einsum("k,kst->st", tree.probabilities, tree.scenarios)   # [6,288]
        dam = tree.point_forecast                                          # raw DAM [6,288]
        rt = _dataset.get_rt_array(d)
        for name in _PRODUCTS:
            p = _NAME_IDX[name]
            bias = eff[p] - rt[p]
            fin = np.isfinite(bias)
            hi = (dam[p] > tau[name]) & fin
            lo = (dam[p] <= tau[name]) & fin
            acc[name]["hi_num"] += float(bias[hi].sum())
            acc[name]["hi_cnt"] += int(hi.sum())
            acc[name]["lo_num"] += float(bias[lo].sum())
            acc[name]["lo_cnt"] += int(lo.sum())
    out = {}
    for name in _PRODUCTS:
        a = acc[name]
        out[name] = {
            "high_bias": a["hi_num"] / a["hi_cnt"] if a["hi_cnt"] else float("nan"),
            "low_bias":  a["lo_num"] / a["lo_cnt"] if a["lo_cnt"] else float("nan"),
            "n_high": a["hi_cnt"], "n_low": a["lo_cnt"],
        }
    return out


# ── Phase 3: rolling stochastic LP with a given forecaster ───────────────────────

def _make_window(fc: BootstrapForecaster, rt_prices: pd.DataFrame):
    trees: dict[date, object] = {}

    def get_tree(d: date):
        if d not in trees:
            trees[d] = fc.forecast(d)
        return trees[d]

    def get_lookahead(h_utc: pd.Timestamp) -> dict:
        d0 = h_utc.date()
        i0 = h_utc.hour * 12
        t0 = get_tree(d0)
        probs = t0.probabilities
        if h_utc.hour == 0:
            window = t0.scenarios
        else:
            t1 = get_tree(d0 + timedelta(days=1))
            window = np.concatenate([t0.scenarios[:, :, i0:], t1.scenarios[:, :, :i0]], axis=2)
        stage1 = window[:, :, :T1].transpose(0, 2, 1)      # [K,T1,6]
        stage2 = window[:, :, T1:].transpose(0, 2, 1)      # [K,T2,6]
        stage1_mean = (probs[:, None, None] * stage1).sum(axis=0)
        return {"stage1_mean": stage1_mean, "stage2_scen": stage2, "probs": probs, "_h": h_utc}

    def solve_hour(la: dict, s_init: float):
        d1, c1, a_ru1, a_rd1, a_rrs1, a_ecrs1, a_ns1, s1_end, _, st = solve_stochastic_hour(
            la["stage1_mean"], la["stage2_scen"], la["probs"], BESS, s_init)
        idx = pd.date_range(la["_h"], periods=T1, freq="5min")
        disp = pd.DataFrame({
            "discharge_mw": d1, "charge_mw": c1, "award_regup_mw": a_ru1,
            "award_regdn_mw": a_rd1, "award_rrs_mw": a_rrs1, "award_ecrs_mw": a_ecrs1,
            "award_nspin_mw": a_ns1}, index=idx)
        disp.index.name = "timestamp_utc"
        return disp, s1_end, st

    return get_lookahead, solve_hour


def _run_eval(fc: BootstrapForecaster, rt_prices: pd.DataFrame, label: str) -> dict:
    print(f"\n=== {label} ===")
    get_la, solve_hr = _make_window(fc, rt_prices)
    res = run_rolling_lp(bess=BESS, rt_prices=rt_prices, get_lookahead_fn=get_la,
                         solve_hour_fn=solve_hr, panel_start=PANEL_START, panel_end=PANEL_END)
    per_day = {}
    for hr in res.hours:
        k = str(hr.hour_utc.date())
        e, a = per_day.get(k, (0.0, 0.0))
        per_day[k] = (e + hr.revenue_energy_usd, a + hr.revenue_as_usd)
    print(f"  Total ${res.revenue_total:,.2f}  (E ${res.revenue_energy:,.0f} / "
          f"AS ${res.revenue_as:,.0f} / Liq ${res.liquidation_revenue:,.0f})  {res.wall_clock_s:.0f}s")
    return {
        "label": label, "revenue_total": res.revenue_total,
        "revenue_energy": res.revenue_energy, "revenue_as": res.revenue_as,
        "liquidation": res.liquidation_revenue,
        "per_day": {k: {"energy": v[0], "as": v[1]} for k, v in per_day.items()},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.perf_counter()
    audit = {}

    # ── PHASE 2.1 — reconstruct train + thresholds ────────────────────────────
    print("=" * 70 + "\nPHASE 2 — Fit DAM AS anchor shrinkage (train Jan 23–Apr 13)\n" + "=" * 70)
    cache, used = _build_proxy_cache(_days(_TRAIN_START, _TRAIN_END))
    print(f"  reconstructed {len(used)} train days")
    tau, tau_hourly = _train_quote_q90(cache, used)
    print("\n  τ_p = q90 DAM quote (5-min) [hourly q90 in brackets]:")
    for n in _PRODUCTS:
        print(f"    {n:<6} τ={tau[n]:7.3f}  [hourly {tau_hourly[n]:7.3f}]  "
              f"Δ={abs(tau[n]-tau_hourly[n]):.4f}")

    # ── PHASE 2.2 — fit s_p (method of moments, proxy) ────────────────────────
    print("\n  Fitting s_p (drive high-regime E[max] bias → 0):")
    fit = {}
    for n in _PRODUCTS:
        s, reason, resid, n_hi = _fit_s(cache, used, n, tau[n])
        b1, _ = _proxy_high_bias(cache, used, n, tau[n], 1.0)
        fit[n] = {"tau": tau[n], "tau_hourly": tau_hourly[n], "s": s, "reason": reason,
                  "high_bias_uncorrected": b1, "high_bias_after": resid, "n_high_train": n_hi}
        print(f"    {n:<6} s={s:.4f} ({reason:14}) high-bias {b1:+.3f} → {resid:+.4f}  "
              f"(n_hi={n_hi})")

    corr = ASAnchorCorrection(tau={n: fit[n]["tau"] for n in _PRODUCTS},
                              shrink={n: fit[n]["s"] for n in _PRODUCTS})
    fc_base = BootstrapForecaster(dataset=_dataset, random_seed=CANONICAL_SEED)
    fc_corr = BootstrapForecaster(dataset=_dataset, random_seed=CANONICAL_SEED,
                                  as_anchor_correction=corr)

    # ── PHASE 2.3 — train-verify through the real forecaster ──────────────────
    print("\n  Train-verify (real k-medoids forecaster) high-regime effective bias:")
    tv_base = _effective_bias_through_forecaster(fc_base, used, tau)
    tv_corr = _effective_bias_through_forecaster(fc_corr, used, tau)
    for n in _PRODUCTS:
        print(f"    {n:<6} high {tv_base[n]['high_bias']:+.3f} → {tv_corr[n]['high_bias']:+.3f}  "
              f"| low {tv_base[n]['low_bias']:+.3f} → {tv_corr[n]['low_bias']:+.3f}  "
              f"(n_hi={tv_corr[n]['n_high']})")

    # ── PHASE 2.4 — VAL MID-GATE ──────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nVAL MID-GATE (Apr 14–19, frozen params)\n" + "=" * 70)
    val_days = _days(_VAL_START, _VAL_END)
    vb = _effective_bias_through_forecaster(fc_base, val_days, tau)
    vc = _effective_bias_through_forecaster(fc_corr, val_days, tau)
    gate_fail = []
    print(f"  {'prod':<6} {'hi_base':>8} {'hi_corr':>8} {'n_hi':>5} | {'lo_base':>8} {'lo_corr':>8} {'lo_Δ':>8}")
    for n in _PRODUCTS:
        hb, hc = vb[n]["high_bias"], vc[n]["high_bias"]
        lb, lc = vb[n]["low_bias"], vc[n]["low_bias"]
        lo_delta = (lc - lb) if np.isfinite(lc) and np.isfinite(lb) else float("nan")
        print(f"  {n:<6} {hb:>8.3f} {hc:>8.3f} {vc[n]['n_high']:>5} | {lb:>8.3f} {lc:>8.3f} {lo_delta:>8.4f}")
        # no-harm: low regime must be ~unchanged
        if np.isfinite(lo_delta) and abs(lo_delta) > 0.05:
            gate_fail.append(f"{n}: low-regime moved {lo_delta:+.3f}")
        # directional: where there are high-regime intervals, |bias| must not grow and sign not flip worse
        if vc[n]["n_high"] >= 20 and np.isfinite(hb) and np.isfinite(hc):
            if abs(hc) > abs(hb) + 1e-6:
                gate_fail.append(f"{n}: high-regime |bias| grew {hb:+.3f}→{hc:+.3f}")
            if hb > 0 and hc < -abs(hb):
                gate_fail.append(f"{n}: high-regime over→under-shoot {hb:+.3f}→{hc:+.3f}")

    if gate_fail:
        audit["phase2"] = {"fit": fit, "train_verify": {"base": tv_base, "corr": tv_corr},
                           "val": {"base": vb, "corr": vc}, "gate_fail": gate_fail}
        (AUDIT_DIR / "w5a_eval.json").write_text(json.dumps(audit, indent=2, default=str))
        raise RuntimeError("VAL MID-GATE FAILED: " + "; ".join(gate_fail) + ". STOP.")
    print("  MID-GATE PASSED — directional improvement + low-regime no-harm.")

    # ── PHASE 3 — eval panel ──────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nPHASE 3 — Eval panel (Apr 20–26, Gurobi)\n" + "=" * 70)
    rt = load_rt_prices()
    base = _run_eval(fc_base, rt, "Baseline (correction disabled)")
    drift = base["revenue_total"] - _BASELINE
    print(f"  Baseline repro drift: ${drift:+,.2f} (tol ±${_REPRO_TOL})")
    if abs(drift) > _REPRO_TOL:
        raise RuntimeError(f"Baseline not reproduced via W5-A harness: drift ${drift:+,.2f}. STOP.")
    corr_run = _run_eval(fc_corr, rt, "Corrected (scarcity anchor shrinkage)")

    d_w5a = corr_run["revenue_total"] - _BASELINE
    recovery = d_w5a / _ORACLE_BOUND
    d_energy = corr_run["revenue_energy"] - base["revenue_energy"]
    d_as     = corr_run["revenue_as"] - base["revenue_as"]
    d_liq    = corr_run["liquidation"] - base["liquidation"]

    print("\n  ── W5-A eval result ──")
    print(f"    Baseline:   ${_BASELINE:,.2f}")
    print(f"    Corrected:  ${corr_run['revenue_total']:,.2f}")
    print(f"    ΔW5A:       ${d_w5a:+,.2f}")
    print(f"    Recovery:   {100*recovery:.1f}% of the ${_ORACLE_BOUND:,.0f} oracle bound")
    print(f"    Components Δ:  energy ${d_energy:+,.0f}  AS ${d_as:+,.0f}  liq ${d_liq:+,.0f}")
    print("\n  Per-day Δ (energy+AS, corrected − baseline):")
    per_day_delta = {}
    for k in sorted(base["per_day"]):
        be = base["per_day"][k]["energy"] + base["per_day"][k]["as"]
        ce = corr_run["per_day"][k]["energy"] + corr_run["per_day"][k]["as"]
        per_day_delta[k] = ce - be
        print(f"    {k}: ${ce-be:+,.2f}   (E {corr_run['per_day'][k]['energy']-base['per_day'][k]['energy']:+,.0f} / "
              f"AS {corr_run['per_day'][k]['as']-base['per_day'][k]['as']:+,.0f})")

    print(f"\n  PF sanity: PF=${_PF:,.0f} UNCHANGED by construction — perfect_foresight "
          f"settles on realized RT and never calls BootstrapForecaster (no forecast input).")

    audit["phase2"] = {"fit": fit, "train_verify": {"base": tv_base, "corr": tv_corr},
                       "val": {"base": vb, "corr": vc}, "gate": "passed"}
    audit["phase3"] = {
        "baseline": base, "corrected": corr_run, "baseline_drift": drift,
        "delta_w5a": d_w5a, "recovery_fraction": recovery, "oracle_bound": _ORACLE_BOUND,
        "delta_energy": d_energy, "delta_as": d_as, "delta_liq": d_liq,
        "per_day_delta": per_day_delta, "pf": _PF, "pf_unchanged_by_construction": True,
    }
    out = AUDIT_DIR / "w5a_eval.json"
    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {out}\nTotal wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
