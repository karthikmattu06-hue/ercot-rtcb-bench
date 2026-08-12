"""W7 — Fern-exclusion sensitivity of the W5-A fitted structure.

PRE-REGISTERED SCOPE. Exactly ONE refit is performed: the W5-A fit procedure re-run on
train-minus-Fern. No other parameter tuning, no new correction form.

**This characterizes a retired lever. No outcome un-retires it. ADR 0014 stands.**

The fit procedure is imported verbatim from `scripts/backtest_w5a_eval.py` — this script
defines no fitting logic of its own:
  - tau_p  = `_train_quote_q90`  (backtest_w5a_eval.py:119) -> q90 of train DAM AS quote, 5-min ffilled
  - s_p    = `_fit_s`            (backtest_w5a_eval.py:151) -> bisection method-of-moments on
                                  the high-regime E[max] effective bias (`_proxy_high_bias`:131)
  - cache  = `_build_proxy_cache`(backtest_w5a_eval.py:108)

Panel runner reused verbatim from `scripts/backtest_w5r.py` (`run_panel`).

Fern window: Jan 23-26, 2026 (ADR 0017 Exhibit 2; DOE emergency-order dates are the
documentary anchor).

SCOPE BOUNDARY (reported, not worked around): Fern is removed from the *fitting sample*
only. The bootstrap analog pool starts 2026-01-09 and is strictly-before-target, so Fern
days remain analog-pool members for every later day. This measures fitting-sample
sensitivity, not the full removal of Fern's influence from the system.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import backtest_w5a_eval as A  # noqa: E402  fit procedure (verbatim)
import backtest_w5r as W       # noqa: E402  panel runner (verbatim)

from ercot_rtcb_bench.forecaster import ASAnchorCorrection, BootstrapForecaster  # noqa: E402

AUDIT = REPO / "data" / "audit"
DATA = REPO / "data" / "processed" / "forecaster"

FERN = [date(2026, 1, 23), date(2026, 1, 24), date(2026, 1, 25), date(2026, 1, 26)]
_TRAIN_START, _TRAIN_END = date(2026, 1, 23), date(2026, 4, 14)   # end exclusive

_COMMITTED = {  # ADR 0012
    "regup": (3.56, 0.15195465087890625),
    "rrs":   (2.71, 0.00125885009765625),
    "ecrs":  (2.56, 0.0374603271484375),
    "nspin": (14.98, 0.0),
}
# committed W5-R panel results (data/audit/w5r_run.json)
_PANELS = {
    "eval_restated":    (date(2026, 4, 20), "Apr 20–26 (eval, restated)", 238_378.80, +18_270),
    "scarcity_confirm": (date(2026, 4, 27), "Apr 27–May 3 (scarcity, confirmatory)", 321_419.73, +6_303),
    "scarcity_primary": (date(2026, 6, 1),  "Jun 1–7 (scarcity, primary)", 87_532.86, -4_765),
    "calm":             (date(2026, 5, 4),  "May 4–10 (calm)", 60_388.34, -10_619),
}
_BASELINE_TOL = 1.00


def load_rt_all() -> pd.DataFrame:
    parts = [pd.read_parquet(DATA / "rt_prices" / f"{m}.parquet").set_index("timestamp_utc")
             for m in ["2026-04", "2026-05", "2026-06"]]
    return pd.concat(parts).sort_index()


def phase1() -> dict:
    print("=" * 78)
    print("PHASE 1 — refit on train-minus-Fern (the single authorised refit)")
    print("=" * 78)
    print("Procedure source (verbatim, no drift):")
    print("  tau_p : backtest_w5a_eval._train_quote_q90   (line 119)")
    print("  s_p   : backtest_w5a_eval._fit_s             (line 151)")
    print("  bias  : backtest_w5a_eval._proxy_high_bias   (line 131)")
    print("  cache : backtest_w5a_eval._build_proxy_cache (line 108)")

    full_days = A._days(_TRAIN_START, _TRAIN_END)
    keep_days = [d for d in full_days if d not in FERN]
    print(f"\n  train window {_TRAIN_START} .. {_TRAIN_END - timedelta(days=1)}  "
          f"= {len(full_days)} days;  minus Fern ({len(FERN)}) = {len(keep_days)} days")

    cache_f, used_f = A._build_proxy_cache(full_days)
    cache_k, used_k = A._build_proxy_cache(keep_days)
    print(f"  reconstructed: full={len(used_f)} days, minus-Fern={len(used_k)} days")

    # ── control: full-train refit must reproduce the committed ADR 0012 fit ──
    tau_f, tauh_f = A._train_quote_q90(cache_f, used_f)
    print("\n  CONTROL — full-train refit vs committed ADR 0012 (harness fidelity):")
    control = {}
    for n in A._PRODUCTS:
        s_f, reason_f, resid_f, nhi_f = A._fit_s(cache_f, used_f, n, tau_f[n])
        ct, cs = _COMMITTED[n]
        ok = abs(tau_f[n] - ct) < 5e-3 and abs(s_f - cs) < 1e-6
        control[n] = {"tau": tau_f[n], "s": s_f, "reason": reason_f,
                      "committed_tau": ct, "committed_s": cs, "reproduces": bool(ok)}
        print(f"    {n:<6} tau={tau_f[n]:8.4f} (cm {ct:7.3f})  s={s_f:.10f} (cm {cs:.10f})  "
              f"{'OK' if ok else 'MISMATCH'}")

    # ── the refit ───────────────────────────────────────────────────────────
    tau_k, tauh_k = A._train_quote_q90(cache_k, used_k)
    fit_k = {}
    print("\n  REFIT — train-minus-Fern:")
    for n in A._PRODUCTS:
        s_k, reason_k, resid_k, nhi_k = A._fit_s(cache_k, used_k, n, tau_k[n])
        fit_k[n] = {"tau": tau_k[n], "tau_hourly": tauh_k[n], "s": s_k,
                    "reason": reason_k, "resid": resid_k, "n_high": nhi_k}
        print(f"    {n:<6} tau'={tau_k[n]:8.4f}  s'={s_k:.10f}  reason={reason_k}  n_hi={nhi_k}")

    # ── comparison ──────────────────────────────────────────────────────────
    print(f"\n  {'product':<8}{'tau':>9}{'tau2':>9}{'d_tau':>9}{'d_tau%':>9}"
          f"{'s':>14}{'s2':>14}{'d_s%':>10}")
    comp = {}
    for n in A._PRODUCTS:
        ct, cs = _COMMITTED[n]
        t2, s2 = fit_k[n]["tau"], fit_k[n]["s"]
        dt_pct = 100 * (t2 - ct) / ct if ct else None
        ds_pct = 100 * (s2 - cs) / cs if cs else None
        comp[n] = {"tau_committed": ct, "tau_refit": t2, "d_tau": t2 - ct, "d_tau_pct": dt_pct,
                   "s_committed": cs, "s_refit": s2, "d_s": s2 - cs, "d_s_pct": ds_pct,
                   "reason_refit": fit_k[n]["reason"]}
        print(f"  {n:<8}{ct:>9.3f}{t2:>9.3f}{t2-ct:>+9.3f}{dt_pct:>+8.1f}%"
              f"{cs:>14.8f}{s2:>14.8f}"
              + (f"{ds_pct:>+9.1f}%" if ds_pct is not None else f"{'n/a':>10}"))

    # ── crossing mass: Fern share of above-threshold intervals ──────────────
    print("\n  CROSSING MASS — Fern share of above-threshold intervals in the FULL train window")
    print("  (DAM-quote basis is the one that determines tau_p; realized-MCPC basis shown for")
    print("   reconciliation with the ADR 0017 Exhibit-2 figures, which used that basis)")
    print(f"\n  {'product':<8}{'above-tau (DAM)':>18}{'Fern share':>12}"
          f"{'above-tau (realized)':>22}{'Fern share':>12}")
    mass = {}
    for n in A._PRODUCTS:
        p = A._NAME_IDX[n]
        dam = np.concatenate([cache_f[d][0][p] for d in used_f])
        rt = np.concatenate([cache_f[d][3][p] for d in used_f])
        isf = np.concatenate([np.full(288, d in FERN) for d in used_f])
        ct = _COMMITTED[n][0]
        hd, hr = dam > ct, (rt > ct) & np.isfinite(rt)
        sd = (hd & isf).sum() / max(hd.sum(), 1)
        sr = (hr & isf).sum() / max(hr.sum(), 1)
        # remaining mass after removing Fern, on the DAM basis, against tau'
        dam_k = np.concatenate([cache_k[d][0][p] for d in used_k])
        rem = int((dam_k > fit_k[n]["tau"]).sum())
        mass[n] = {"dam_above_tau": int(hd.sum()), "dam_fern": int((hd & isf).sum()),
                   "dam_fern_share": float(sd), "realized_above_tau": int(hr.sum()),
                   "realized_fern": int((hr & isf).sum()), "realized_fern_share": float(sr),
                   "dam_above_tauprime_after_exclusion": rem,
                   "train_days_fern_frac": len(FERN) / len(used_f)}
        print(f"  {n:<8}{int(hd.sum()):>18,}{100*sd:>11.1f}%{int(hr.sum()):>22,}{100*sr:>11.1f}%")
    print(f"\n  (Fern = {len(FERN)}/{len(used_f)} train days = "
          f"{100*len(FERN)/len(used_f):.1f}% by duration)")

    return {"train_days_full": len(used_f), "train_days_minus_fern": len(used_k),
            "fern_window": [str(d) for d in FERN],
            "control_full_train_refit": control, "refit_minus_fern": fit_k,
            "comparison": comp, "crossing_mass": mass,
            "procedure_source": {
                "tau_p": "backtest_w5a_eval._train_quote_q90 (line 119)",
                "s_p": "backtest_w5a_eval._fit_s (line 151)",
                "bias": "backtest_w5a_eval._proxy_high_bias (line 131)",
                "cache": "backtest_w5a_eval._build_proxy_cache (line 108)"}}


def phase2(p1: dict) -> dict:
    print("\n" + "=" * 78)
    print("PHASE 2 — four committed W5-R panels re-run under (tau', s'), frozen")
    print("=" * 78)
    fit_k = p1["refit_minus_fern"]
    corr2 = ASAnchorCorrection(tau={n: fit_k[n]["tau"] for n in A._PRODUCTS},
                               shrink={n: fit_k[n]["s"] for n in A._PRODUCTS})
    print("  frozen at refit values (no further tuning): "
          + ", ".join(f"{n} tau'={fit_k[n]['tau']:.3f}/s'={fit_k[n]['s']:.6f}" for n in A._PRODUCTS))

    rt = load_rt_all()
    fc_base = BootstrapForecaster(dataset=W._dataset, random_seed=42)
    fc_corr2 = BootstrapForecaster(dataset=W._dataset, random_seed=42, as_anchor_correction=corr2)

    out = {}
    for key, (mon, label, base_committed, delta_committed) in _PANELS.items():
        res = W.run_panel(fc_base, fc_corr2, rt, mon, label)
        got = res["baseline"]["revenue_total"]
        drift = got - base_committed
        ok = abs(drift) <= _BASELINE_TOL
        print(f"    baseline byte-check: got ${got:,.2f}  committed ${base_committed:,.2f}  "
              f"drift {drift:+.5f}  {'MATCH' if ok else 'MISMATCH'}")
        res["baseline_check"] = {"got": got, "committed": base_committed,
                                 "drift": drift, "match": bool(ok)}
        res["delta_committed"] = delta_committed
        res["delta_refit"] = res["delta_total"]
        res["sign_committed"] = int(np.sign(delta_committed))
        res["sign_refit"] = int(np.sign(res["delta_total"]))
        res["sign_unchanged"] = bool(res["sign_committed"] == res["sign_refit"])
        print(f"    delta' = ${res['delta_total']:+,.2f}   committed delta = ${delta_committed:+,.0f}   "
              f"sign {'UNCHANGED' if res['sign_unchanged'] else 'FLIPPED'}")
        print(f"    per-day d': " + "  ".join(
            f"{k[-5:]}:{v['delta']:+,.0f}" for k, v in sorted(res["per_day_delta"].items())))
        out[key] = res

    print("\n  " + "=" * 74)
    print(f"  {'panel':<38}{'committed d':>14}{'refit d2':>14}{'sign':>10}")
    for key, (_m, label, _b, dc) in _PANELS.items():
        r = out[key]
        print(f"  {label:<38}{dc:>+14,.0f}{r['delta_total']:>+14,.0f}"
              f"{('same' if r['sign_unchanged'] else 'FLIP'):>10}")
    n_same = sum(1 for r in out.values() if r["sign_unchanged"])
    print(f"\n  sign pattern preserved on {n_same}/4 panels")
    return out


def main() -> None:
    t0 = time.perf_counter()
    p1 = phase1()
    p2 = phase2(p1)
    audit = {"scope": "Fern-exclusion sensitivity; ONE refit (train-minus-Fern); "
                      "characterization of a RETIRED lever; ADR 0014 stands regardless",
             "scope_boundary": "Fern removed from fitting sample only; remains in the "
                               "bootstrap analog pool (POOL_START 2026-01-09)",
             "phase1_refit": p1, "phase2_panels": p2,
             "sign_pattern_preserved": sum(1 for r in p2.values() if r["sign_unchanged"]),
             "n_panels": len(p2)}
    (AUDIT / "w7_fern.json").write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {AUDIT / 'w7_fern.json'}\nTotal wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
