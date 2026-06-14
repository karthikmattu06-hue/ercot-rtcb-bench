"""W5-B precheck — cross-panel stability of the evening-peak LMP bias (go/no-go).

DIAGNOSTIC ONLY. No fix, no correction, no intervention LP. Read-only on realized.

Window (verbatim from W4-A / ADR 0010): evening peak = HoD 0 and 1 UTC (7–8 pm CDT),
= the first 24 five-min intervals of each UTC day (HoD0 = 0–11, HoD1 = 12–23). W4-A eval
bias forecast−realized = −$48.77 (HoD0) / −$47.25 (HoD1), i.e. NEGATIVE (under-forecast).

Bias quantity: forecast LMP − realized LMP over the evening-peak intervals, per panel.
Forecast LMP = probability-weighted scenario mean of series 0 (the LP's stage-2 LMP
planning quantity — LMP has no non-negativity/E[max] clip, so the raw mean bias and the
revenue-relevant planning-quantity bias COINCIDE; reported as one).

Panels: eval Apr 20–26 + the 6 eligible weeks, on the re-pinned canonical data.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ercot_rtcb_bench.forecaster import BootstrapForecaster, ForecasterDataset  # noqa: E402

AUDIT = REPO / "data" / "audit"
EVENING_PEAK = list(range(24))   # HoD 0 (0–11) + HoD 1 (12–23) UTC
W4A_SIGN = -1                    # forecast < realized (under-forecast) on the eval panel

_PANELS = {
    "eval (Apr 20–26)":          date(2026, 4, 20),
    "Apr 27–May 3 (scar-conf)":  date(2026, 4, 27),
    "May 4–10 (calm)":           date(2026, 5, 4),
    "May 11–17":                 date(2026, 5, 11),
    "May 18–24":                 date(2026, 5, 18),
    "May 25–31":                 date(2026, 5, 25),
    "Jun 1–7 (scar-primary)":    date(2026, 6, 1),
}

_dataset = ForecasterDataset()
_fc = BootstrapForecaster(dataset=_dataset, random_seed=42)


def _day_peak_bias(d: date) -> tuple[float, np.ndarray, dict]:
    """Per-day evening-peak mean bias + interval biases + per-HoD means (cross-check)."""
    tree = _fc.forecast(d)
    f_lmp = np.einsum("k,kt->t", tree.probabilities, tree.scenarios[:, 0, :])  # [288]
    r_lmp = _dataset.get_rt_array(d)[0]                                         # [288]
    bias = f_lmp - r_lmp
    pk = bias[EVENING_PEAK]
    r_pk = r_lmp[EVENING_PEAK]
    m = np.isfinite(pk) & np.isfinite(r_pk)
    pk = pk[m]
    hod = {
        "hod0": float(np.nanmean((f_lmp[0:12] - r_lmp[0:12])[np.isfinite(f_lmp[0:12] - r_lmp[0:12])])),
        "hod1": float(np.nanmean((f_lmp[12:24] - r_lmp[12:24])[np.isfinite(f_lmp[12:24] - r_lmp[12:24])])),
    }
    return (float(pk.mean()) if pk.size else float("nan")), pk, hod


def main() -> None:
    print("=" * 72)
    print("W5-B PRECHECK — evening-peak LMP bias (HoD 0–1 UTC), forecast − realized")
    print("Window verbatim from W4-A/ADR 0010; bias<0 = under-forecast (W4-A eval sign)")
    print("=" * 72)

    panels = {}
    for label, mon in _PANELS.items():
        day_biases, all_pk = [], []
        for i in range(7):
            d = mon + timedelta(days=i)
            db, pk, hod = _day_peak_bias(d)
            day_biases.append({"date": str(d), "bias": db, "hod0": hod["hod0"], "hod1": hod["hod1"]})
            all_pk.append(pk)
        pk_all = np.concatenate(all_pk)
        panel_bias = float(pk_all.mean())
        dbs = np.array([x["bias"] for x in day_biases])
        # intra-panel sign consistency: how many of 7 days share the panel sign
        psign = np.sign(panel_bias)
        same_sign_days = int((np.sign(dbs) == psign).sum())
        panels[label] = {
            "mon": str(mon), "panel_bias": panel_bias,
            "n_intervals": int(pk_all.size),
            "within_window_std": float(pk_all.std()),
            "per_day": day_biases,
            "per_day_bias_std": float(dbs.std()),
            "days_sharing_panel_sign": same_sign_days,
            "max_abs_day_bias": float(np.abs(dbs).max()),
        }

    # ── Per-panel table ───────────────────────────────────────────────────────
    print(f"\n{'panel':<26}{'bias $/MWh':>11}{'sign':>6}{'n':>5}{'within-σ':>10}"
          f"{'day-σ':>9}{'days same-sign':>15}")
    biases = []
    for label, p in panels.items():
        biases.append(p["panel_bias"])
        sgn = "−" if p["panel_bias"] < 0 else "+"
        print(f"  {label:<24}{p['panel_bias']:>+11.2f}{sgn:>6}{p['n_intervals']:>5}"
              f"{p['within_window_std']:>10.1f}{p['per_day_bias_std']:>9.1f}"
              f"{p['days_sharing_panel_sign']:>12}/7")

    # eval cross-check vs W4-A (HoD0 −48.77 / HoD1 −47.25)
    ev = panels["eval (Apr 20–26)"]["per_day"]
    h0 = float(np.mean([x["hod0"] for x in ev]))
    h1 = float(np.mean([x["hod1"] for x in ev]))
    print(f"\n  eval cross-check vs W4-A: HoD0 mean {h0:+.2f} (W4-A −48.77), "
          f"HoD1 mean {h1:+.2f} (W4-A −47.25)")

    # ── Cross-panel stability metrics ─────────────────────────────────────────
    b = np.array(biases)
    n_neg = int((b < 0).sum())
    n_pos = int((b > 0).sum())
    flips = min(n_neg, n_pos)
    med = float(np.median(b))
    cv = float(np.std(b) / abs(np.mean(b))) if abs(np.mean(b)) > 1e-9 else float("inf")
    print("\n" + "=" * 72)
    print("CROSS-PANEL STABILITY")
    print("=" * 72)
    print(f"  1. Sign stability: {n_neg}/7 share W4-A sign (negative); {n_pos}/7 positive. "
          f"sign-flips = {flips}")
    print(f"  2. Magnitude: min {b.min():+.2f}  median {med:+.2f}  max {b.max():+.2f}  "
          f"mean {b.mean():+.2f}  CV {cv:.2f}")
    print(f"  3. Within-window concentration: per-panel days-sharing-sign = "
          f"{[panels[k]['days_sharing_panel_sign'] for k in panels]}")

    # ── Go/no-go (spec mapping: sign-flips is the gate) ───────────────────────
    # GO         : sign stable (≥6/7 same sign, ≤1 flip) AND magnitude same order (CV low)
    # CONDITIONAL: sign stable (≤1 flip) BUT magnitude highly variable (CV high)
    # NO-GO      : sign flips across panels (≥2 panels opposite sign)
    if flips <= 1:
        rec = ("GO — sign stable (≥6/7) and magnitude same order; build W5-B "
               "replication-native") if cv < 1.0 else (
               "CONDITIONAL — sign stable (≥6/7) but magnitude highly variable; only a "
               "partial/shrunk correction of the robust component may survive — "
               "full-bias targeting (the W5-A mistake) will not")
    else:
        rec = (f"NO-GO — the evening-peak LMP bias FLIPS SIGN across panels "
               f"({n_neg} negative / {n_pos} positive, {flips} flips); cross-panel mean "
               f"≈ ${b.mean():+.2f}/MWh (~0) with ±$30–48 swings. A static evening-peak "
               f"LMP fix is dead on arrival — same failure mode as the retired AS lever "
               f"(ADR 0014): a concentrated bias whose realization (here, even the sign) "
               f"is week-to-week unstable. The W4-A eval −$48 episode is NOT "
               f"representative (the adjacent week over-forecasts +$30). PIVOT: a "
               f"conditional/state-dependent correction, or retire W5-B as a second "
               f"documented negative result.")
    print(f"\n  RECOMMENDATION: {rec}")

    out = AUDIT / "w5b_precheck.json"
    out.write_text(json.dumps({
        "window": "HoD 0-1 UTC (first 24 intervals); forecast-realized; bias<0=under-forecast",
        "panels": panels, "eval_crosscheck": {"hod0": h0, "hod1": h1},
        "cross_panel": {"n_negative": n_neg, "n_positive": n_pos, "sign_flips": flips,
                        "min": float(b.min()), "max": float(b.max()), "median": med,
                        "mean": float(b.mean()), "cv": cv},
        "recommendation": rec,
    }, indent=2, default=str))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
