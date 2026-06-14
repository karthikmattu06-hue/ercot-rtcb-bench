"""W5-R-run — out-of-sample replication of the AS anchor lever (FROZEN params).

No refit. Loads (τ_p, s_p) from the committed w5a_eval.json, asserts equality to the
ADR 0012 values, and runs the rolling Stochastic LP (flag off / on) + PF on the
pre-registered replication panels:

  eval (restated)        : Apr 20–26   (baseline re-pinned to $238,378.80, ADR 0013)
  scarcity (primary)     : Jun 1–7     (376 τ_p-qualifying intervals)
  calm                   : May 4–10    (187, fewest)
  scarcity (confirmatory): Apr 27–May 3 (341)

Reuses the panel runner from backtest_w5r (run_panel: baseline/corrected/PF, per-day,
worst-day). τ_p metric: qualifying interval = realized RT MCPC > τ_p for ANY product.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import backtest_w5r as W  # noqa: E402  load_frozen_correction, run_panel, qualifying_count

from ercot_rtcb_bench.forecaster import BootstrapForecaster  # noqa: E402

AUDIT = REPO / "data" / "audit"
DATA  = REPO / "data" / "processed" / "forecaster"

# committed ADR 0012 / W5-R-verify values (exact)
_COMMITTED = {
    "regup": (3.56, 0.15195465087890625),
    "rrs":   (2.71, 0.00125885009765625),
    "ecrs":  (2.56, 0.0374603271484375),
    "nspin": (14.98, 0.0),
}
_EVAL_BASELINE_REPINNED = 238_378.80   # ADR 0013

_PANELS = {
    "eval_restated":      (date(2026, 4, 20), "Apr 20–26 (eval, restated)"),
    "scarcity_primary":   (date(2026, 6, 1),  "Jun 1–7 (scarcity, primary)"),
    "calm":               (date(2026, 5, 4),  "May 4–10 (calm)"),
    "scarcity_confirm":   (date(2026, 4, 27), "Apr 27–May 3 (scarcity, confirmatory)"),
}
_ALL_WEEKS = [date(2026, 4, 27), date(2026, 5, 4), date(2026, 5, 11),
              date(2026, 5, 18), date(2026, 5, 25), date(2026, 6, 1)]


def load_rt_all() -> pd.DataFrame:
    parts = [pd.read_parquet(DATA / "rt_prices" / f"{m}.parquet").set_index("timestamp_utc")
             for m in ["2026-04", "2026-05", "2026-06"]]
    return pd.concat(parts).sort_index()


def per_day_qualifying(mon: date, tau: dict) -> dict:
    """τ_p-qualifying interval count per day of the week (scarcity concentration)."""
    import numpy as np
    out = {}
    for i in range(7):
        d = mon + timedelta(days=i)
        rt = W._dataset.get_rt_array(d)
        comb = np.zeros(rt.shape[1], dtype=bool)
        for n in ["regup", "rrs", "ecrs", "nspin"]:
            v = rt[W._NAME_IDX[n]]
            comb |= (np.isfinite(v) & (v > tau[n]))
        out[str(d)] = int(comb.sum())
    return out


def main() -> None:
    t0 = time.perf_counter()
    corr, fit = W.load_frozen_correction()

    # ── Assert frozen params == ADR 0012 (no refit) ───────────────────────────
    print("=" * 70 + "\nFROZEN parameters (from w5a_eval.json) — asserting == ADR 0012:")
    for n in ["regup", "rrs", "ecrs", "nspin"]:
        ct, cs = _COMMITTED[n]
        assert abs(corr.tau[n] - ct) < 1e-9, f"{n} τ drift"
        assert abs(corr.shrink[n] - cs) < 1e-12, f"{n} s drift"
        print(f"  {n:<6} τ={corr.tau[n]:7.3f}  s={corr.shrink[n]:.8f}  ✓")
    print("  All four match ADR 0012 exactly — NO refit.")
    tau = corr.tau

    # ── 6-week τ_p qualifying counts (auditability) ───────────────────────────
    print("\n6-week τ_p qualifying counts (realized MCPC > τ_p, any product):")
    week_counts = {}
    for mon in _ALL_WEEKS:
        qc = W.qualifying_count(mon, tau)
        week_counts[str(mon)] = qc
        print(f"  {mon}: {qc['qualifying']:>4}/{qc['total']}  per-product {qc['per_product']}")

    # ── Runs ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nPANEL RUNS (Gurobi)\n" + "=" * 70)
    rt = load_rt_all()
    fc_base = BootstrapForecaster(dataset=W._dataset, random_seed=42)
    fc_corr = BootstrapForecaster(dataset=W._dataset, random_seed=42, as_anchor_correction=corr)

    panels = {}
    for key, (mon, label) in _PANELS.items():
        res = W.run_panel(fc_base, fc_corr, rt, mon, label)
        res["per_day_qualifying"] = per_day_qualifying(mon, tau)
        # mechanism: both E and AS up? scarcity-day concentration?
        pdq = res["per_day_qualifying"]
        scarce_day = max(pdq, key=pdq.get)
        res["mechanism"] = {
            "both_up": (res["delta_energy"] > 0 and res["delta_as"] > 0),
            "delta_energy": res["delta_energy"], "delta_as": res["delta_as"],
            "top_scarcity_day": scarce_day, "top_scarcity_qual": pdq[scarce_day],
            "delta_on_top_scarcity_day": res["per_day_delta"].get(scarce_day, {}).get("delta"),
        }
        panels[key] = res

    # ── Cross-panel synthesis ─────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nCROSS-PANEL SYNTHESIS\n" + "=" * 70)
    print(f"  {'panel':<32}{'Δ':>12}{'Δ/PFhead':>10}{'worst-day':>12}{'E/AS up':>9}")
    synth = {}
    for key, (_mon, label) in _PANELS.items():
        r = panels[key]
        b = r["baseline"]["revenue_total"]   # measured panel baseline (flag off)
        head = r["pf"] - b
        d = r["delta_total"]
        worst = r["worst_day"]
        synth[key] = {"label": label, "delta": d, "pf": r["pf"], "baseline": b,
                      "delta_pct_headroom": (d / head if head else None),
                      "worst_day": worst, "both_up": r["mechanism"]["both_up"],
                      "top_scarcity_day": r["mechanism"]["top_scarcity_day"],
                      "delta_on_top_scarcity_day": r["mechanism"]["delta_on_top_scarcity_day"]}
        print(f"  {label:<32}{d:>+12,.0f}{100*(d/head if head else 0):>9.1f}%"
              f"{worst['delta']:>+12,.0f}{str(r['mechanism']['both_up']):>9}")

    # verdict logic (reported; interpretation in chat)
    sp = panels["scarcity_primary"]["delta_total"]
    sc = panels["scarcity_confirm"]["delta_total"]
    if sp > 0 and sc > 0:
        verdict = "BOTH scarcity panels Δ>0 — lever replicates (not a one-day artifact)"
    elif sp > 0 or sc > 0:
        verdict = "ONE scarcity panel positive — lever real but high-variance; no v0.2 claim without more panels"
    else:
        verdict = "BOTH scarcity panels Δ≤0 — lever does NOT replicate out-of-sample"
    print(f"\n  Pre-registered verdict: {verdict}")
    print(f"  Calm worst-day ${panels['calm']['worst_day']['delta']:+,.0f} "
          f"(vs W5-A Apr 24 precedent −$5,524) — downside bounded? "
          f"{'yes' if panels['calm']['worst_day']['delta'] > -5524 else 'no'}")

    audit = {
        "frozen_params": {n: {"tau": corr.tau[n], "s": corr.shrink[n]} for n in ["regup","rrs","ecrs","nspin"]},
        "eval_baseline_repinned": _EVAL_BASELINE_REPINNED,
        "week_qualifying_counts": week_counts,
        "panels": {k: dict(v) for k, v in panels.items()},
        "synthesis": synth, "verdict": verdict,
    }
    out = AUDIT / "w5r_run.json"
    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {out}\nTotal wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
