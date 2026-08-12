"""W6 — July seasonal test of the ADR 0015 non-stationarity claims.

PRE-REGISTERED. No refit, no fix-building, no new correction. Everything reused from
the W5-A/W5-B/W5-R harnesses so the definitions are identical by construction:

  - evening-peak window + bias quantity : diagnose_w5b_precheck (W4-A/ADR 0010 verbatim)
  - tau_p qualifying metric             : backtest_w5r.qualifying_count (frozen tau_p)
  - per-week gap %                      : backtest_w5r.week_integrity
  - panel runner (base/corrected/PF)    : backtest_w5r.run_panel
  - frozen (tau_p, s_p)                 : w5a_eval.json, asserted == ADR 0012

Phases:
  0  coverage + per-week gap gate + no-regression eval-baseline check
  1  tau_p qualifying counts for every eligible July week (spring counts printed alongside)
  2A evening-peak LMP bias extended over spring + summer; cross-panel stats
  2B frozen AS lever on the summer scarcity + calm panels

Interpretation happens in chat against the three pre-registered criteria. This script
reports; it does not decide.
"""

from __future__ import annotations

import argparse
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

import backtest_w5r as W  # noqa: E402
from ercot_rtcb_bench.forecaster import BootstrapForecaster  # noqa: E402

AUDIT = REPO / "data" / "audit"
DATA = REPO / "data" / "processed" / "forecaster"

# ── Pre-registered constants (fixed before results) ─────────────────────────────
_COMMITTED = {                       # ADR 0012 values
    "regup": (3.56, 0.15195465087890625),
    "rrs":   (2.71, 0.00125885009765625),
    "ecrs":  (2.56, 0.0374603271484375),
    "nspin": (14.98, 0.0),
}
_EVAL_MON = date(2026, 4, 20)
_EVAL_BASELINE_REPINNED = 238_378.80      # ADR 0013
_NOREG_TOL = 1.00                         # +/- $1

_GAP_GATE = 0.005                         # <=0.5% missing per series

# July candidate weeks (Mon-Sun), each with its Sun+1 UTC tail inside the pull window
_JULY_WEEKS = [date(2026, 6, 29), date(2026, 7, 6), date(2026, 7, 13),
               date(2026, 7, 20), date(2026, 7, 27)]

# Spring reference (committed w5r_run.json / w5b_precheck.json)
_SPRING_COUNTS = {"2026-04-27": 341, "2026-05-04": 187, "2026-05-11": 200,
                  "2026-05-18": 234, "2026-05-25": 280, "2026-06-01": 376}
_SPRING_BIAS_PANELS = {                   # label -> Monday (W5-B set, verbatim)
    "eval (Apr 20–26)":         date(2026, 4, 20),
    "Apr 27–May 3 (scar-conf)": date(2026, 4, 27),
    "May 4–10 (calm)":          date(2026, 5, 4),
    "May 11–17":                date(2026, 5, 11),
    "May 18–24":                date(2026, 5, 18),
    "May 25–31":                date(2026, 5, 25),
    "Jun 1–7 (scar-primary)":   date(2026, 6, 1),
}

EVENING_PEAK = list(range(24))            # HoD 0 (0-11) + HoD 1 (12-23) UTC
_MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


def _wk(mon: date) -> str:
    return f"{mon} – {mon + timedelta(days=6)}"


def load_rt_all() -> pd.DataFrame:
    parts = []
    for m in _MONTHS:
        p = DATA / "rt_prices" / f"{m}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p).set_index("timestamp_utc"))
    return pd.concat(parts).sort_index()


# ── Phase 0 ─────────────────────────────────────────────────────────────────────

def phase0(rt: pd.DataFrame, run_noreg: bool) -> dict:
    print("=" * 78)
    print("PHASE 0 — coverage, per-week gap gate, no-regression check")
    print("=" * 78)

    cov = {}
    for series, sub in [("rt", "rt_prices"), ("dam", "dam_prices"), ("sys", "system_conditions")]:
        last = None
        for m in _MONTHS:
            p = DATA / sub / f"{m}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p)
            ts = pd.to_datetime(df["timestamp_utc"], utc=True)
            val = df.drop(columns=["timestamp_utc"])
            fin = ts[val.notna().any(axis=1)]
            if len(fin):
                last = max(last, fin.max()) if last is not None else fin.max()
        cov[series] = str(last)
        print(f"  {series:<4} latest finite: {last}")

    print(f"\n  {'candidate week':<26}{'worst-series gap %':>20}{'eligible':>10}")
    weeks = {}
    for mon in _JULY_WEEKS:
        wi = W.week_integrity(mon)
        worst = max(v["frac"] for v in wi.values())
        elig = worst <= _GAP_GATE
        weeks[str(mon)] = {"week": _wk(mon), "worst_gap_frac": worst,
                           "per_series": {k: v["frac"] for k, v in wi.items()},
                           "eligible": bool(elig)}
        print(f"  {_wk(mon):<26}{100*worst:>19.3f}%{str(elig):>10}")

    n_elig = sum(1 for v in weeks.values() if v["eligible"])
    print(f"\n  eligible July weeks: {n_elig}/{len(_JULY_WEEKS)}  (gate: <= {100*_GAP_GATE}% missing)")

    noreg = {"ran": False}
    if run_noreg:
        print("\n  no-regression: re-running eval panel Apr 20–26 (flag OFF)...")
        fc = BootstrapForecaster(dataset=W._dataset, random_seed=42)
        base = W.run_stochastic(fc, rt, _EVAL_MON, "no-regression baseline")
        got = base["revenue_total"]
        drift = got - _EVAL_BASELINE_REPINNED
        ok = abs(drift) <= _NOREG_TOL
        noreg = {"ran": True, "target": _EVAL_BASELINE_REPINNED, "got": got,
                 "drift": drift, "tol": _NOREG_TOL, "pass": bool(ok),
                 "components": {"energy": base["revenue_energy"], "as": base["revenue_as"],
                                "liq": base["liquidation"]}}
        print(f"    eval baseline = ${got:,.5f}  target ${_EVAL_BASELINE_REPINNED:,.2f}  "
              f"drift {drift:+.5f}  tol +/-${_NOREG_TOL:.2f}  GATE: {'PASS' if ok else 'FAIL'}")

    return {"coverage": cov, "weeks": weeks, "n_eligible": n_elig, "no_regression": noreg}


# ── Phase 1 ─────────────────────────────────────────────────────────────────────

def phase1(tau: dict, eligible: list[date]) -> dict:
    print("\n" + "=" * 78)
    print("PHASE 1 — tau_p qualifying counts (realized MCPC > frozen tau_p, any product)")
    print("=" * 78)
    print("\n  SPRING (committed, w5r_run.json):")
    for k, v in _SPRING_COUNTS.items():
        print(f"    {k}: {v:>4}/2016")

    print("\n  SUMMER (this run):")
    counts = {}
    for mon in eligible:
        qc = W.qualifying_count(mon, tau)
        counts[str(mon)] = qc
        print(f"    {mon}: {qc['qualifying']:>4}/{qc['total']}  per-product {qc['per_product']}")

    if not counts:
        return {"summer": {}, "spring": _SPRING_COUNTS, "scarcity": None, "calm": None}

    # mechanical selection: most = scarcity, fewest = calm; ties -> earlier week
    order = sorted(counts.items(), key=lambda kv: (-kv[1]["qualifying"], kv[0]))
    scarcity = order[0][0]
    calm = sorted(counts.items(), key=lambda kv: (kv[1]["qualifying"], kv[0]))[0][0]
    sv = [v["qualifying"] for v in counts.values()]
    spring_v = list(_SPRING_COUNTS.values())
    print(f"\n  SELECTED  summer scarcity panel = {scarcity} ({counts[scarcity]['qualifying']})")
    print(f"            summer calm panel     = {calm} ({counts[calm]['qualifying']})")
    print(f"\n  summer range {min(sv)}–{max(sv)}   vs   spring range {min(spring_v)}–{max(spring_v)}")
    return {"summer": counts, "spring": _SPRING_COUNTS, "scarcity": scarcity, "calm": calm,
            "summer_min": min(sv), "summer_max": max(sv),
            "spring_min": min(spring_v), "spring_max": max(spring_v)}


# ── Phase 2A ────────────────────────────────────────────────────────────────────

def _day_peak_bias(fc, d: date):
    tree = fc.forecast(d)
    f_lmp = np.einsum("k,kt->t", tree.probabilities, tree.scenarios[:, 0, :])
    r_lmp = W._dataset.get_rt_array(d)[0]
    bias = f_lmp - r_lmp
    pk = bias[EVENING_PEAK]
    pk = pk[np.isfinite(pk)]
    d0 = f_lmp[0:12] - r_lmp[0:12]
    d1 = f_lmp[12:24] - r_lmp[12:24]
    hod = {"hod0": float(np.nanmean(d0[np.isfinite(d0)])),
           "hod1": float(np.nanmean(d1[np.isfinite(d1)]))}
    return (float(pk.mean()) if pk.size else float("nan")), pk, hod


def phase2a(eligible: list[date]) -> dict:
    print("\n" + "=" * 78)
    print("PHASE 2A — evening-peak LMP bias (HoD 0–1 UTC), forecast − realized")
    print("W4-A/ADR 0010 window verbatim; bias<0 = under-forecast")
    print("=" * 78)
    fc = BootstrapForecaster(dataset=W._dataset, random_seed=42)

    labels = dict(_SPRING_BIAS_PANELS)
    for mon in eligible:
        labels[f"{mon.strftime('%b %-d')}–{(mon+timedelta(days=6)).strftime('%b %-d')} (summer)"] = mon

    panels = {}
    print(f"\n  {'panel':<30}{'bias $/MWh':>12}{'sign':>6}{'n':>7}{'day-σ':>9}{'same-sign':>11}")
    for label, mon in labels.items():
        days, allpk = [], []
        for i in range(7):
            d = mon + timedelta(days=i)
            db, pk, hod = _day_peak_bias(fc, d)
            days.append({"date": str(d), "bias": db, **hod})
            allpk.append(pk)
        pk_all = np.concatenate(allpk)
        pb = float(pk_all.mean())
        dbs = np.array([x["bias"] for x in days])
        same = int((np.sign(dbs) == np.sign(pb)).sum())
        panels[label] = {"mon": str(mon), "panel_bias": pb, "n_intervals": int(pk_all.size),
                         "per_day": days, "per_day_bias_std": float(dbs.std()),
                         "days_sharing_panel_sign": same,
                         "max_abs_day_bias": float(np.abs(dbs).max()),
                         "season": "summer" if mon >= date(2026, 6, 29) else "spring"}
        print(f"  {label:<30}{pb:>+12.2f}{('−' if pb < 0 else '+'):>6}{pk_all.size:>7}"
              f"{dbs.std():>9.1f}{same:>9}/7")

    def _stats(sel):
        b = np.array([panels[k]["panel_bias"] for k in sel])
        neg, pos = int((b < 0).sum()), int((b > 0).sum())
        mean = float(b.mean())
        return {"n_panels": len(b), "n_negative": neg, "n_positive": pos,
                "sign_flips": min(neg, pos), "min": float(b.min()), "max": float(b.max()),
                "median": float(np.median(b)), "mean": mean,
                "cv": float(np.std(b) / abs(mean)) if abs(mean) > 1e-9 else float("inf")}

    spring_k = [k for k, v in panels.items() if v["season"] == "spring"]
    summer_k = [k for k, v in panels.items() if v["season"] == "summer"]
    stats = {"full": _stats(list(panels)), "spring_only": _stats(spring_k)}
    if summer_k:
        stats["summer_only"] = _stats(summer_k)

    print("\n  CROSS-PANEL STATS")
    for name, s in stats.items():
        print(f"    {name:<13} n={s['n_panels']}  {s['n_negative']}neg/{s['n_positive']}pos  "
              f"flips={s['sign_flips']}  mean {s['mean']:+.2f}  median {s['median']:+.2f}  "
              f"min {s['min']:+.2f}  max {s['max']:+.2f}  CV {s['cv']:.2f}")
    return {"panels": panels, "stats": stats}


# ── Phase 2B ────────────────────────────────────────────────────────────────────

def phase2b(rt: pd.DataFrame, corr, tau: dict, sel: dict) -> dict:
    print("\n" + "=" * 78)
    print("PHASE 2B — FROZEN AS lever on the summer scarcity + calm panels")
    print("=" * 78)
    if not sel.get("scarcity"):
        print("  no eligible summer week — skipped")
        return {}

    fc_base = BootstrapForecaster(dataset=W._dataset, random_seed=42)
    fc_corr = BootstrapForecaster(dataset=W._dataset, random_seed=42, as_anchor_correction=corr)

    targets = {"summer_scarcity": date.fromisoformat(sel["scarcity"])}
    if sel["calm"] != sel["scarcity"]:
        targets["summer_calm"] = date.fromisoformat(sel["calm"])

    out = {}
    for key, mon in targets.items():
        res = W.run_panel(fc_base, fc_corr, rt, mon, key)
        pdq = {}
        for i in range(7):
            d = mon + timedelta(days=i)
            a = W._dataset.get_rt_array(d)
            comb = np.zeros(a.shape[1], dtype=bool)
            for n in ["regup", "rrs", "ecrs", "nspin"]:
                v = a[W._NAME_IDX[n]]
                comb |= (np.isfinite(v) & (v > tau[n]))
            pdq[str(d)] = int(comb.sum())
        res["per_day_qualifying"] = pdq
        top = max(pdq, key=pdq.get)
        res["mechanism"] = {
            "both_up": bool(res["delta_energy"] > 0 and res["delta_as"] > 0),
            "delta_energy": res["delta_energy"], "delta_as": res["delta_as"],
            "delta_liq": res["delta_liq"],
            "top_scarcity_day": top, "top_scarcity_qual": pdq[top],
            "delta_on_top_scarcity_day": res["per_day_delta"].get(top, {}).get("delta"),
        }
        print(f"    components  ΔE=${res['delta_energy']:+,.0f}  ΔAS=${res['delta_as']:+,.0f}  "
              f"ΔLiq=${res['delta_liq']:+,.0f}   E&AS both up: {res['mechanism']['both_up']}")
        print(f"    per-day Δ: " + "  ".join(
            f"{k[-5:]}:{v['delta']:+,.0f}" for k, v in sorted(res["per_day_delta"].items())))
        out[key] = res
    return out


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="0,1,2a,2b")
    ap.add_argument("--skip-noreg", action="store_true")
    args = ap.parse_args()
    ph = set(args.phase.split(","))
    t0 = time.perf_counter()

    corr, _fit = W.load_frozen_correction()
    print("=" * 78)
    print("FROZEN parameters (from committed w5a_eval.json) — asserting == ADR 0012:")
    for n in ["regup", "rrs", "ecrs", "nspin"]:
        ct, cs = _COMMITTED[n]
        assert abs(corr.tau[n] - ct) < 1e-9, f"{n} tau drift vs ADR 0012"
        assert abs(corr.shrink[n] - cs) < 1e-12, f"{n} s drift vs ADR 0012"
        print(f"  {n:<6} tau={corr.tau[n]:7.3f}  s={corr.shrink[n]:.17f}  == ADR 0012 OK")
    print("  All four match ADR 0012 exactly — NO refit.")
    tau = corr.tau

    rt = load_rt_all()
    audit = {"frozen_params": {n: {"tau": corr.tau[n], "s": corr.shrink[n]}
                               for n in ["regup", "rrs", "ecrs", "nspin"]},
             "frozen_params_assert": "equal to ADR 0012 (tolerance 1e-9 tau / 1e-12 s)"}

    p0 = phase0(rt, run_noreg=("0" in ph and not args.skip_noreg)) if "0" in ph else {}
    audit["phase0"] = p0
    if p0.get("no_regression", {}).get("ran") and not p0["no_regression"]["pass"]:
        (AUDIT / "w6_seasonal.json").write_text(json.dumps(audit, indent=2, default=str))
        raise SystemExit("STOP — no-regression gate FAILED; state written, no workaround.")

    eligible = [date.fromisoformat(k) for k, v in p0.get("weeks", {}).items() if v["eligible"]]
    if "0" in ph and len(eligible) < 1:
        (AUDIT / "w6_seasonal.json").write_text(json.dumps(audit, indent=2, default=str))
        raise SystemExit("STOP — no eligible July week; coverage report written.")

    sel = phase1(tau, eligible) if "1" in ph else {}
    audit["phase1_selection"] = sel
    if "2a" in ph:
        audit["phase2a_bias"] = phase2a(eligible)
    if "2b" in ph:
        audit["phase2b_as_lever"] = phase2b(rt, corr, tau, sel)

    (AUDIT / "w6_seasonal.json").write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {AUDIT / 'w6_seasonal.json'}\nTotal wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
