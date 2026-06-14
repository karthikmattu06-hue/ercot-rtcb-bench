"""W5-R: two-panel out-of-sample replication of the W5-A AS anchor shrinkage.

NO refit, NO forecaster/LP changes, NO ADR. The correction parameters (τ_p, s_p) are
read FROZEN from data/audit/w5a_eval.json (committed W5-A fit) and applied unchanged.

Phase 0  recon + integrity: data coverage, candidate Mon–Sun weeks from Apr 27,
         eligibility (rolling tail needs next-day data), per-series missing counts,
         analog-pool leakage convention, per-product scarcity thresholds.
Phase 1  pre-registered selection: scarcity = most qualifying intervals, calm = fewest
         (qualifying = realized RT MCPC of ANY product > its train top-decile threshold).
Phase 2  per selected panel: Stochastic LP baseline (flag off) + corrected (flag on,
         frozen) + PF; Δ, components, per-day deltas, worst-day loss, mechanism.

Threshold note: w5a_diagnostic.json does NOT store a per-product realized-price
threshold; "train top-decile threshold per product" is recomputed here as the q90 of
realized RT MCPC per product on the W5-A train window (Jan 23–Apr 13) — the faithful
reading. Flagged in the report.
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
from ercot_rtcb_bench.forecaster.analog import POOL_START
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.perfect_foresight import _PRICE_COLS, perfect_foresight
from ercot_rtcb_bench.methods.rolling_lp import T1, run_rolling_lp
from ercot_rtcb_bench.methods.stochastic_lp import solve_stochastic_hour

AUDIT_DIR = Path(__file__).parent.parent / "data" / "audit"
DATA_DIR  = Path(__file__).parent.parent / "data" / "processed" / "forecaster"
BESS      = BESSParams.default_100mw_4hr()

_AS_NAMES = ["regup", "rrs", "ecrs", "nspin"]                 # corrected products
_NAME_IDX = {"regup": 1, "rrs": 3, "ecrs": 4, "nspin": 5}
_ALL_AS   = {"regup": 1, "regdn": 2, "rrs": 3, "ecrs": 4, "nspin": 5}
_SERIES   = ["lmp", "mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]

_TRAIN_START = date(2026, 1, 23)
_TRAIN_END   = date(2026, 4, 14)   # exclusive → through Apr 13
_FIRST_PANEL_MON = date(2026, 4, 27)

_dataset = ForecasterDataset()


# ── Frozen correction (read from committed W5-A audit) ───────────────────────────

def load_frozen_correction() -> tuple[ASAnchorCorrection, dict]:
    fit = json.loads((AUDIT_DIR / "w5a_eval.json").read_text())["phase2"]["fit"]
    tau = {n: fit[n]["tau"] for n in _AS_NAMES}
    shrink = {n: fit[n]["s"] for n in _AS_NAMES}
    return ASAnchorCorrection(tau=tau, shrink=shrink), fit


def load_rt() -> pd.DataFrame:
    parts = [pd.read_parquet(DATA_DIR / "rt_prices" / f"{m}.parquet").set_index("timestamp_utc")
             for m in ["2026-04", "2026-05"]]
    return pd.concat(parts).sort_index()


# ── Phase 0 ─────────────────────────────────────────────────────────────────────

def _day_present(d: date) -> bool:
    """Day forecastable as a target: has any DAM AS quote (anchor)."""
    dam = _dataset.get_dam_array(d)
    return bool(np.isfinite(dam[1:6]).any())


def coverage() -> dict:
    """Latest finite timestamp per series across the loaded months."""
    cov = {}
    for series, sub, cols in [("rt", "rt_prices", _SERIES),
                              ("dam", "dam_prices", None),
                              ("sys", "system_conditions", ["net_load_mw"])]:
        last = None
        for m in ["2026-04", "2026-05"]:
            df = pd.read_parquet(DATA_DIR / sub / f"{m}.parquet")
            if "timestamp_utc" in df.columns:
                df = df.set_index("timestamp_utc")
            df.index = pd.to_datetime(df.index, utc=True)
            use = [c for c in (cols or df.columns) if c in df.columns]
            fin = df[use].dropna(how="all")
            if len(fin):
                last = fin.index.max() if last is None else max(last, fin.index.max())
        cov[series] = str(last)
    return cov


def candidate_weeks() -> list[tuple[date, date, bool, str]]:
    """Mon–Sun weeks from Apr 27. Eligible iff the week's days are present AND the
    rolling tail day (Sun+1) is forecastable (needs DAM for the last-hour window)."""
    out, mon = [], _FIRST_PANEL_MON
    while True:
        sun = mon + timedelta(days=6)
        days = [mon + timedelta(days=i) for i in range(7)]
        week_present = all(_day_present(d) for d in days)
        if not week_present:
            break
        tail = sun + timedelta(days=1)
        tail_ok = _day_present(tail)
        reason = "ok" if tail_ok else f"tail {tail} absent (rolling window needs next-day tree)"
        out.append((mon, sun, tail_ok, reason))
        mon = mon + timedelta(days=7)
    return out


def week_integrity(mon: date) -> dict:
    """Missing-interval fraction per series across the 7-day week."""
    miss = {s: 0 for s in _SERIES}
    total = 0
    for i in range(7):
        d = mon + timedelta(days=i)
        panel = _dataset.get_day(d)
        total += len(panel)
        for s in _SERIES:
            miss[s] += int(panel[s].isna().sum())
    return {s: {"missing": miss[s], "frac": miss[s] / max(total, 1)} for s in _SERIES}


def train_thresholds() -> dict:
    """q90 of realized RT MCPC per product on the W5-A train window (Jan 23–Apr 13)."""
    pools = {n: [] for n in _AS_NAMES}
    d = _TRAIN_START
    while d < _TRAIN_END:
        rt = _dataset.get_rt_array(d)
        for n in _AS_NAMES:
            v = rt[_NAME_IDX[n]]
            pools[n].append(v[np.isfinite(v)])
        d += timedelta(days=1)
    return {n: float(np.quantile(np.concatenate(pools[n]), 0.90)) for n in _AS_NAMES}


# ── Phase 1 ─────────────────────────────────────────────────────────────────────

def qualifying_count(mon: date, thr: dict) -> dict:
    """Intervals where ANY product's realized MCPC exceeds its train threshold."""
    any_hi = 0
    per_prod = {n: 0 for n in _AS_NAMES}
    total = 0
    for i in range(7):
        d = mon + timedelta(days=i)
        rt = _dataset.get_rt_array(d)
        masks = {}
        for n in _AS_NAMES:
            v = rt[_NAME_IDX[n]]
            m = np.isfinite(v) & (v > thr[n])
            per_prod[n] += int(m.sum())
            masks[n] = m
        combined = np.zeros(rt.shape[1], dtype=bool)
        for n in _AS_NAMES:
            combined |= masks[n]
        any_hi += int(combined.sum())
        total += rt.shape[1]
    return {"qualifying": any_hi, "total": total, "per_product": per_prod}


# ── Phase 2 ─────────────────────────────────────────────────────────────────────

def _make_window(fc: BootstrapForecaster):
    trees: dict[date, object] = {}

    def get_tree(d: date):
        if d not in trees:
            trees[d] = fc.forecast(d)
        return trees[d]

    def get_lookahead(h: pd.Timestamp) -> dict:
        d0, i0 = h.date(), h.hour * 12
        t0 = get_tree(d0)
        probs = t0.probabilities
        if h.hour == 0:
            window = t0.scenarios
        else:
            window = np.concatenate(
                [t0.scenarios[:, :, i0:], get_tree(d0 + timedelta(days=1)).scenarios[:, :, :i0]], axis=2)
        s1 = window[:, :, :T1].transpose(0, 2, 1)
        s2 = window[:, :, T1:].transpose(0, 2, 1)
        return {"stage1_mean": (probs[:, None, None] * s1).sum(0), "stage2_scen": s2,
                "probs": probs, "_h": h}

    def solve_hour(la: dict, s_init: float):
        d1, c1, a1, a2, a3, a4, a5, s_end, _, st = solve_stochastic_hour(
            la["stage1_mean"], la["stage2_scen"], la["probs"], BESS, s_init)
        idx = pd.date_range(la["_h"], periods=T1, freq="5min")
        disp = pd.DataFrame({"discharge_mw": d1, "charge_mw": c1, "award_regup_mw": a1,
                             "award_regdn_mw": a2, "award_rrs_mw": a3, "award_ecrs_mw": a4,
                             "award_nspin_mw": a5}, index=idx)
        disp.index.name = "timestamp_utc"
        return disp, s_end, st

    return get_lookahead, solve_hour


def run_stochastic(fc: BootstrapForecaster, rt: pd.DataFrame, mon: date, label: str) -> dict:
    ps = pd.Timestamp(mon, tz="UTC")
    pe = pd.Timestamp(mon + timedelta(days=7), tz="UTC")
    get_la, solve_hr = _make_window(fc)
    res = run_rolling_lp(bess=BESS, rt_prices=rt.ffill().bfill(), get_lookahead_fn=get_la,
                         solve_hour_fn=solve_hr, panel_start=ps, panel_end=pe)
    per_day = {}
    for hr in res.hours:
        k = str(hr.hour_utc.date())
        e, a = per_day.get(k, (0.0, 0.0))
        per_day[k] = (e + hr.revenue_energy_usd, a + hr.revenue_as_usd)
    print(f"    {label}: ${res.revenue_total:,.2f}  (E ${res.revenue_energy:,.0f} / "
          f"AS ${res.revenue_as:,.0f} / Liq ${res.liquidation_revenue:,.0f})")
    return {"revenue_total": res.revenue_total, "revenue_energy": res.revenue_energy,
            "revenue_as": res.revenue_as, "liquidation": res.liquidation_revenue,
            "per_day": {k: {"energy": v[0], "as": v[1]} for k, v in per_day.items()}}


def run_pf(rt: pd.DataFrame, mon: date) -> float:
    ps = pd.Timestamp(mon, tz="UTC")
    pe = pd.Timestamp(mon + timedelta(days=7), tz="UTC")
    sl = rt[(rt.index >= ps) & (rt.index < pe)][_PRICE_COLS].ffill().bfill()
    return float(perfect_foresight(BESS, sl).revenue_total)


def run_panel(fc_base, fc_corr, rt, mon, kind) -> dict:
    print(f"\n  === {kind} panel {mon} – {mon+timedelta(days=6)} ===")
    base = run_stochastic(fc_base, rt, mon, "baseline (flag off)")
    corr = run_stochastic(fc_corr, rt, mon, "corrected (frozen)")
    pf = run_pf(rt, mon)
    d_total = corr["revenue_total"] - base["revenue_total"]
    per_day_delta, worst = {}, (None, 0.0)
    for k in sorted(base["per_day"]):
        be = base["per_day"][k]["energy"] + base["per_day"][k]["as"]
        ce = corr["per_day"][k]["energy"] + corr["per_day"][k]["as"]
        per_day_delta[k] = {"delta": ce - be,
                            "d_energy": corr["per_day"][k]["energy"] - base["per_day"][k]["energy"],
                            "d_as": corr["per_day"][k]["as"] - base["per_day"][k]["as"]}
        if (ce - be) < worst[1]:
            worst = (k, ce - be)
    print(f"    Δ total = ${d_total:+,.2f}   PF=${pf:,.0f}   worst day {worst[0]} ${worst[1]:+,.2f}")
    return {"kind": kind, "week": [str(mon), str(mon + timedelta(days=6))],
            "baseline": base, "corrected": corr, "pf": pf,
            "delta_total": d_total,
            "delta_energy": corr["revenue_energy"] - base["revenue_energy"],
            "delta_as": corr["revenue_as"] - base["revenue_as"],
            "delta_liq": corr["liquidation"] - base["liquidation"],
            "per_day_delta": per_day_delta, "worst_day": {"date": worst[0], "delta": worst[1]}}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.perf_counter()
    corr, fit = load_frozen_correction()
    print("=" * 70 + "\nFROZEN correction (from committed w5a_eval.json):")
    for n in _AS_NAMES:
        print(f"  {n:<6} τ={corr.tau[n]:7.3f}  s={corr.shrink[n]:.6f}")

    # ── PHASE 0 ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nPHASE 0 — recon + integrity\n" + "=" * 70)
    cov = coverage()
    print("  Data coverage (latest finite ts):")
    for k, v in cov.items():
        print(f"    {k}: {v}")
    print(f"  Analog pool: dynamic, strictly-before-target  [{POOL_START}, target_day)  "
          f"→ leakage-safe; grows for later weeks. Correction params FROZEN (no refit).")

    cands = candidate_weeks()
    thr = train_thresholds()
    print("\n  Train top-decile thresholds (q90 realized RT MCPC, Jan 23–Apr 13; "
          "recomputed — not stored in w5a_diagnostic.json):")
    for n in _AS_NAMES:
        print(f"    {n:<6} {thr[n]:.3f}")

    print("\n  Candidate weeks + integrity:")
    integ = {}
    eligible = []
    for mon, sun, tail_ok, reason in cands:
        ig = week_integrity(mon)
        worst_frac = max(v["frac"] for v in ig.values())
        gap_ok = worst_frac <= 0.005
        elig = tail_ok and gap_ok
        integ[str(mon)] = {"sun": str(sun), "tail_ok": tail_ok, "reason": reason,
                           "worst_gap_frac": worst_frac, "gap_ok": gap_ok, "eligible": elig,
                           "integrity": ig}
        if elig:
            eligible.append(mon)
        print(f"    {mon}–{sun}  eligible={elig}  worst_gap={worst_frac*100:.3f}%  "
              f"tail_ok={tail_ok}  ({reason})")

    # Qualifying counts for ALL candidates (auditable, reported even on STOP) ──
    print("\n  Qualifying-interval counts (context; realized MCPC > train q90, any product):")
    counts = {}
    for mon, _sun, _tail_ok, _r in cands:
        qc = qualifying_count(mon, thr)
        counts[str(mon)] = {**qc, "eligible": (mon in eligible)}
        flag = "" if mon in eligible else "  (INELIGIBLE)"
        print(f"    {mon}: qualifying={qc['qualifying']:>5} / {qc['total']}  "
              f"per-product {qc['per_product']}{flag}")

    if not eligible:
        out = AUDIT_DIR / "w5r_replication.json"
        out.write_text(json.dumps({
            "STOP": "no eligible candidate week — data ingestion is the prerequisite",
            "frozen_correction": {"tau": corr.tau, "shrink": corr.shrink},
            "phase0": {"coverage": cov, "thresholds": thr,
                       "pool_convention": f"dynamic strictly-before-target [{POOL_START}, target)",
                       "candidates": integ},
            "phase1_context_counts": counts,
        }, indent=2, default=str))
        print("\n" + "=" * 70)
        print("PHASE 0 STOP — no eligible week (all candidates exceed the 0.5% gap rule).")
        print("Data effectively ends ~May 11 (RT/DAM); ingestion is the prerequisite chunk.")
        print("Per the pre-registered rule, NOT deviating to run an ineligible week.")
        print(f"Wrote {out}")
        return

    # ── PHASE 1 — selection ───────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nPHASE 1 — pre-registered selection\n" + "=" * 70)

    elig_counts = [(m, counts[str(m)]["qualifying"]) for m in eligible]
    scarcity_mon = sorted(elig_counts, key=lambda x: (-x[1], x[0]))[0][0]   # max; ties→earlier
    calm_mon     = sorted(elig_counts, key=lambda x: (x[1], x[0]))[0][0]    # min; ties→earlier
    # drivers of scarcity count
    drivers = counts[str(scarcity_mon)]["per_product"]
    print(f"\n  SCARCITY panel = {scarcity_mon} (most qualifying: {counts[str(scarcity_mon)]['qualifying']})")
    print(f"  CALM panel     = {calm_mon} (fewest qualifying: {counts[str(calm_mon)]['qualifying']})")
    print(f"  Scarcity drivers (per-product qualifying counts): {drivers}")
    if scarcity_mon == calm_mon:
        print("  NOTE: only one eligible week — scarcity and calm coincide.")

    # ── PHASE 2 — runs ────────────────────────────────────────────────────────
    print("\n" + "=" * 70 + "\nPHASE 2 — runs (Gurobi)\n" + "=" * 70)
    rt = load_rt()
    fc_base = BootstrapForecaster(dataset=_dataset, random_seed=42)
    fc_corr = BootstrapForecaster(dataset=_dataset, random_seed=42, as_anchor_correction=corr)

    panels = {}
    panels["scarcity"] = run_panel(fc_base, fc_corr, rt, scarcity_mon, "scarcity")
    if calm_mon != scarcity_mon:
        panels["calm"] = run_panel(fc_base, fc_corr, rt, calm_mon, "calm")

    audit = {
        "frozen_correction": {"tau": corr.tau, "shrink": corr.shrink},
        "phase0": {"coverage": cov, "thresholds": thr,
                   "pool_convention": f"dynamic strictly-before-target [{POOL_START}, target)",
                   "candidates": integ},
        "phase1": {"counts": counts, "scarcity": str(scarcity_mon), "calm": str(calm_mon),
                   "scarcity_drivers": drivers},
        "phase2": panels,
    }
    out = AUDIT_DIR / "w5r_replication.json"
    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {out}\nTotal wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
