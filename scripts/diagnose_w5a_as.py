"""W5-A: AS effective-price diagnostic (Phase 0 reproduction + Phase 1 bias).

RECON / PHASE 0 / PHASE 1 ONLY. No forecaster or LP changes; no fix. Phase 2
(the fix) is authorized separately. Eval panel (Apr 20–26) is NEVER read here.

Windows (W3-D convention):
  train = forecastable days through Apr 13, 2026   (pool = [Jan 9, target))
  val   = Apr 14–19, 2026                           (item 5 preview only)
  eval  = Apr 20–26, 2026                            (LOCKED — untouched)

Forecast quantities per (product p ∈ {regup,regdn,rrs,ecrs,nspin}, interval t):
  F_dam[p,t]  = DAM AS MCPC point forecast (the raw day-ahead anchor; tree.point_forecast)
  F_eff[p,t]  = Σ_k probs_k · scenarios[k,p,t]  = the probability-weighted mean of the
                (already clipped ≥0) bootstrap scenarios.  Because the non-negativity
                clip is applied at scenario construction (bootstrap.py), this equals the
                E[max(price,0)] effective price the stochastic LP plans on (W4-A def,
                δ=0 baseline).  So F_eff IS the effective-price view (Phase 1 item 3).
  realized    = RT MCPC (dataset.get_rt_array).

Phase 0: reproduce baseline Stochastic LP = $238,376 (no oracle). Report solver.

Phase 1 (train window, + val preview): per product —
  (1) mean bias overall & by hour-of-day, additive (F−R) and ratio (meanF/meanR)
  (2) bias by system state: net-load quartile and realized-LMP quartile (scarcity proxy)
  (3) effective-price (F_eff) bias vs raw-DAM (F_dam) bias; non-negativity binding via
      the fraction of scenario cells pinned at the 0 floor (where raw↔effective diverge)
  (4) error concentration: top-decile share of |revenue-weighted bias| (|F−R|·realized MCPC)
  (5) val-window preview of (1)+(2)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.forecaster.forecaster import CANONICAL_SEED, BootstrapForecaster

AUDIT_DIR = Path(__file__).parent.parent / "data" / "audit"

# Series indices / names (price col order: lmp, regup, regdn, rrs, ecrs, nspin)
_LMP_IDX   = 0
_AS_IDX    = [1, 2, 3, 4, 5]
_AS_NAMES  = ["regup", "regdn", "rrs", "ecrs", "nspin"]

# Windows
_TRAIN_END = date(2026, 4, 14)   # exclusive → through Apr 13
_VAL_START = date(2026, 4, 14)
_VAL_END   = date(2026, 4, 20)   # exclusive → Apr 14–19
_TRAIN_SCAN_START = date(2026, 1, 23)  # ~2wk pool depth before first forecast attempt

_BASELINE_EXPECTED = 238_376.27
_BASELINE_TOL      = 1.00
_ZERO_FLOOR        = 1e-6        # scenario value treated as pinned-at-0 below this

_dataset = ForecasterDataset()
_fc      = BootstrapForecaster(dataset=_dataset, random_seed=CANONICAL_SEED)


# ── Collection ────────────────────────────────────────────────────────────────

def _forecastable_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d < end:
        days.append(d)
        d += timedelta(days=1)
    return days


def collect_window(days: list[date], label: str) -> dict:
    """Forecast each day; gather per-product flattened forecast/realized arrays.

    Returns dict with per-product arrays and book-keeping. Eval days never appear.
    """
    print(f"\n--- collecting {label} ({days[0]}..{days[-1]}, {len(days)} candidate days) ---")
    f_eff   = {n: [] for n in _AS_NAMES}
    f_dam   = {n: [] for n in _AS_NAMES}
    realized = {n: [] for n in _AS_NAMES}
    hour    = {n: [] for n in _AS_NAMES}
    netload = {n: [] for n in _AS_NAMES}
    lmp_rz  = {n: [] for n in _AS_NAMES}
    clip_frac = {n: np.zeros(24) for n in _AS_NAMES}   # Σ pinned cells per HoD
    clip_cnt  = {n: np.zeros(24) for n in _AS_NAMES}   # Σ cells per HoD
    used_days, skipped = [], []

    hours_idx = np.repeat(np.arange(24), 12)           # [288] hour-of-day per interval

    for d in days:
        try:
            tree = _fc.forecast(d)
        except Exception as e:  # noqa: BLE001 — diagnostic: log + skip thin/early pools
            skipped.append((str(d), type(e).__name__))
            continue
        if tree.scenarios.shape[0] < 5:
            skipped.append((str(d), f"K={tree.scenarios.shape[0]}"))
            continue

        scen  = tree.scenarios                         # [K,6,288] clipped ≥0
        probs = tree.probabilities                     # [K]
        dam   = tree.point_forecast                    # [6,288] DAM
        rt    = _dataset.get_rt_array(d)               # [6,288] realized (may hold NaN)
        nl    = _dataset.get_net_load(d)               # [288] (may hold NaN)
        lmp   = rt[_LMP_IDX]                            # [288]
        eff   = np.einsum("k,kst->st", probs, scen)    # [6,288] effective forecast

        # Raw values stored as-is (NaN included); product_stats finite-masks per cell.
        used_days.append(str(d))
        for j, p in enumerate(_AS_IDX):
            n = _AS_NAMES[j]
            f_eff[n].append(eff[p])
            f_dam[n].append(dam[p])
            realized[n].append(rt[p])
            hour[n].append(hours_idx)
            netload[n].append(nl)
            lmp_rz[n].append(lmp)
            # non-negativity binding: fraction of scenario cells pinned at 0 per HoD
            pinned = (scen[:, p, :] <= _ZERO_FLOOR)     # [K,288]
            for h in range(24):
                sl = slice(h * 12, (h + 1) * 12)
                clip_frac[n][h] += float(pinned[:, sl].sum())
                clip_cnt[n][h]  += float(pinned[:, sl].size)

    out = {"label": label, "used_days": used_days, "skipped": skipped}
    for n in _AS_NAMES:
        out[n] = {
            "f_eff":   np.concatenate(f_eff[n])   if f_eff[n]   else np.array([]),
            "f_dam":   np.concatenate(f_dam[n])   if f_dam[n]   else np.array([]),
            "realized": np.concatenate(realized[n]) if realized[n] else np.array([]),
            "hour":    np.concatenate(hour[n])    if hour[n]    else np.array([]),
            "netload": np.concatenate(netload[n]) if netload[n] else np.array([]),
            "lmp":     np.concatenate(lmp_rz[n])  if lmp_rz[n]  else np.array([]),
            "clip_pinned_frac_byhod": (clip_frac[n] / np.maximum(clip_cnt[n], 1)).tolist(),
        }
    print(f"  used {len(used_days)} days, skipped {len(skipped)}")
    return out


# ── Bias statistics ─────────────────────────────────────────────────────────────

def _ratio(f: np.ndarray, r: np.ndarray) -> float:
    mr = float(r.mean())
    return float(f.mean() / mr) if abs(mr) > 1e-9 else float("nan")


def _quartile_bins(x: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """Rank-based equal-count quartiles (tie-robust; always 4 populated bins).

    x must already be finite. Returns (bin_index ∈ {0..3}, value thresholds).
    """
    n = len(x)
    order = np.argsort(x, kind="stable")
    ranks = np.empty(n, dtype=np.int64)
    ranks[order] = np.arange(n)
    bins = np.minimum(ranks * 4 // n, 3)
    qs = [float(q) for q in np.quantile(x, [0.25, 0.5, 0.75])]
    return bins, qs


def product_stats(col: dict) -> dict:
    f_eff, f_dam = col["f_eff"], col["f_dam"]
    r, h, nl, lmp = col["realized"], col["hour"], col["netload"], col["lmp"]
    # Drop any interval with a non-finite value in any field (rare gaps).
    mask = (np.isfinite(f_eff) & np.isfinite(f_dam) & np.isfinite(r)
            & np.isfinite(nl) & np.isfinite(lmp))
    f_eff, f_dam, r, h, nl, lmp = (
        f_eff[mask], f_dam[mask], r[mask], h[mask], nl[mask], lmp[mask]
    )
    bias_eff = f_eff - r
    bias_dam = f_dam - r

    # (1) overall + by hour-of-day
    byhod = []
    for hh in range(24):
        m = h == hh
        byhod.append({
            "hod": hh,
            "bias_eff": float(bias_eff[m].mean()),
            "bias_dam": float(bias_dam[m].mean()),
            "ratio_eff": _ratio(f_eff[m], r[m]),
            "mean_realized": float(r[m].mean()),
        })

    # (2) state bins
    nl_bin, nl_q = _quartile_bins(nl)
    lmp_bin, lmp_q = _quartile_bins(lmp)
    by_netload = [{
        "quartile": q, "bias_eff": float(bias_eff[nl_bin == q].mean()),
        "n": int((nl_bin == q).sum()), "mean_realized": float(r[nl_bin == q].mean()),
    } for q in range(4)]
    by_lmp = [{
        "quartile": q, "bias_eff": float(bias_eff[lmp_bin == q].mean()),
        "mean_realized_mcpc": float(r[lmp_bin == q].mean()),
        "mean_lmp": float(lmp[lmp_bin == q].mean()), "n": int((lmp_bin == q).sum()),
    } for q in range(4)]

    # (4) error concentration: revenue-weighted |bias| = |F_eff−R| · realized MCPC
    rev_wt_bias = np.abs(bias_eff) * np.maximum(r, 0.0)
    total = float(rev_wt_bias.sum())
    if total > 0:
        srt = np.sort(rev_wt_bias)[::-1]
        top_n = max(1, int(0.10 * len(srt)))
        top_decile_share = float(srt[:top_n].sum() / total)
    else:
        top_decile_share = float("nan")

    return {
        "n_intervals": int(len(r)),
        "overall": {
            "bias_eff": float(bias_eff.mean()),
            "bias_dam": float(bias_dam.mean()),
            "ratio_eff": _ratio(f_eff, r),
            "ratio_dam": _ratio(f_dam, r),
            "mean_forecast_eff": float(f_eff.mean()),
            "mean_forecast_dam": float(f_dam.mean()),
            "mean_realized": float(r.mean()),
            "mae_eff": float(np.abs(bias_eff).mean()),
        },
        "by_hour": byhod,
        "by_netload_quartile": {"thresholds": nl_q, "bins": by_netload},
        "by_lmp_quartile": {"thresholds": lmp_q, "bins": by_lmp},
        "concentration": {
            "rev_weighted_top_decile_share": top_decile_share,
            "definition": "|F_eff - realized| * max(realized_MCPC,0); top 10% of intervals share of total",
        },
        "clip_pinned_frac_byhod": col["clip_pinned_frac_byhod"],
    }


# ── Phase 0 ─────────────────────────────────────────────────────────────────────

def run_phase0() -> dict:
    print("\n" + "=" * 70)
    print("PHASE 0 — Baseline Stochastic LP reproduction (HARD GATE)")
    print("=" * 70)
    from backtest_w4a import load_rt_prices, run_oracle_stochastic
    rt = load_rt_prices()
    res, _edge = run_oracle_stochastic(rt, fix_lmp=False, fix_as=False,
                                       label="Baseline Stochastic LP (no oracle)")
    rev = res["revenue_total"]
    drift = rev - _BASELINE_EXPECTED
    print(f"\n  Baseline reproduced: ${rev:,.2f}")
    print(f"  Expected:            ${_BASELINE_EXPECTED:,.2f}")
    print(f"  Drift:               ${drift:+,.2f}  (tol ±${_BASELINE_TOL:.2f})")
    print("  Solver: Gurobi (license active)")
    if abs(drift) > _BASELINE_TOL:
        raise RuntimeError(
            f"Phase 0 baseline reproduction FAILED: drift ${drift:+,.2f} "
            f"exceeds ±${_BASELINE_TOL:.2f}. STOP — report discrepancy."
        )
    print("  GATE PASSED — baseline reproduces (Gurobi).")
    return {"baseline_revenue": rev, "expected": _BASELINE_EXPECTED,
            "drift": drift, "solver": "gurobi"}


# ── Phase 1 ─────────────────────────────────────────────────────────────────────

def run_phase1() -> dict:
    print("\n" + "=" * 70)
    print("PHASE 1 — AS forecast bias diagnostic")
    print("=" * 70)
    train_days = _forecastable_days(_TRAIN_SCAN_START, _TRAIN_END)
    val_days   = _forecastable_days(_VAL_START, _VAL_END)

    train = collect_window(train_days, "train")
    val   = collect_window(val_days, "val")

    train_stats = {n: product_stats(train[n]) for n in _AS_NAMES}
    val_stats   = {n: product_stats(val[n]) for n in _AS_NAMES}

    # ── Print summary tables ──────────────────────────────────────────────────
    print("\n=== TRAIN overall bias (forecast − realized, $/MW-h) ===")
    print(f"  {'product':<7} {'bias_eff':>9} {'bias_dam':>9} {'ratio_eff':>9} "
          f"{'meanF_eff':>9} {'meanR':>8} {'MAE':>7} {'topDec%':>8}")
    for n in _AS_NAMES:
        o = train_stats[n]["overall"]
        c = train_stats[n]["concentration"]["rev_weighted_top_decile_share"]
        print(f"  {n:<7} {o['bias_eff']:>9.3f} {o['bias_dam']:>9.3f} {o['ratio_eff']:>9.3f} "
              f"{o['mean_forecast_eff']:>9.3f} {o['mean_realized']:>8.3f} {o['mae_eff']:>7.3f} "
              f"{100*c:>7.1f}%")

    print("\n=== TRAIN bias by realized-LMP quartile (scarcity proxy), bias_eff ===")
    print(f"  {'product':<7} {'Q1(low)':>9} {'Q2':>9} {'Q3':>9} {'Q4(high)':>9}")
    for n in _AS_NAMES:
        b = train_stats[n]["by_lmp_quartile"]["bins"]
        print(f"  {n:<7} " + " ".join(f"{b[q]['bias_eff']:>9.3f}" for q in range(4)))

    print("\n=== TRAIN bias by net-load quartile, bias_eff ===")
    print(f"  {'product':<7} {'Q1(low)':>9} {'Q2':>9} {'Q3':>9} {'Q4(high)':>9}")
    for n in _AS_NAMES:
        b = train_stats[n]["by_netload_quartile"]["bins"]
        print(f"  {n:<7} " + " ".join(f"{b[q]['bias_eff']:>9.3f}" for q in range(4)))

    print("\n=== VAL overall bias (out-of-sample stability check) ===")
    print(f"  {'product':<7} {'bias_eff':>9} {'bias_dam':>9} {'ratio_eff':>9}")
    for n in _AS_NAMES:
        o = val_stats[n]["overall"]
        print(f"  {n:<7} {o['bias_eff']:>9.3f} {o['bias_dam']:>9.3f} {o['ratio_eff']:>9.3f}")

    return {
        "train": {"window": [str(_TRAIN_SCAN_START), str(_TRAIN_END - timedelta(days=1))],
                  "used_days": train["used_days"], "skipped": train["skipped"],
                  "stats": train_stats},
        "val": {"window": [str(_VAL_START), str(_VAL_END - timedelta(days=1))],
                "used_days": val["used_days"], "skipped": val["skipped"],
                "stats": val_stats},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["0", "1", "all"], default="all")
    args = ap.parse_args()
    t0 = time.perf_counter()

    audit = {}
    out = AUDIT_DIR / "w5a_diagnostic.json"
    if out.exists():
        audit = json.loads(out.read_text())

    if args.phase in ("0", "all"):
        audit["phase0"] = run_phase0()
    if args.phase in ("1", "all"):
        audit["phase1"] = run_phase1()

    out.write_text(json.dumps(audit, indent=2, default=str))
    print(f"\nWrote {out}")
    print(f"Total wall clock: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
