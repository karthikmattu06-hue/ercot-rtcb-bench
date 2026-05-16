#!/usr/bin/env python3
"""W3-B Task 5 — Backtest of the bootstrap probabilistic forecaster.

Primary panel: Apr 20–26, 2026 (settled, 7 operating days).
Optional secondary panel: Feb 1–7, 2026 (early-regime stress test).

Metrics (per series):
  - Mean-trajectory bias: E[p̂] − p_realized (probability-weighted mean minus realized)
  - CRPS: Continuous Ranked Probability Score (generalizes MAE to full distribution)
  - 80% interval coverage: fraction of realized prices inside the [10th, 90th] quantile

Output: docs/backtest_w3b.md (markdown table) + data/audit/backtest_w3b.json

Usage:
    python scripts/backtest_w3b.py                              # primary panel only
    python scripts/backtest_w3b.py --panel secondary            # Feb 1-7 only
    python scripts/backtest_w3b.py --panel both                 # primary + secondary
    python scripts/backtest_w3b.py --start 2026-04-20 --end 2026-04-27  # custom range
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest_w3b")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ercot_rtcb_bench.forecaster import BootstrapForecaster, ForecasterDataset
from ercot_rtcb_bench.forecaster.scenario_tree import SERIES_NAMES, N_STEPS

# ── CRPS computation ──────────────────────────────────────────────────────────

def crps_ensemble(
    scenarios: np.ndarray,  # [K, T]
    probs: np.ndarray,       # [K]
    realized: np.ndarray,   # [T]
) -> np.ndarray:
    """Compute CRPS for each time step, averaged across the interval.

    CRPS(F, y) = E_F[|X - y|] - 0.5 * E_F[|X - X'|]
    where X, X' ~ F are independent draws.

    Parameters
    ----------
    scenarios : [K, T]
    probs : [K]
    realized : [T]

    Returns
    -------
    crps_mean : float scalar — mean CRPS across T time steps
    """
    k, t = scenarios.shape
    # Expand for broadcasting: [K, T]
    y = realized[None, :]  # [1, T]

    # E[|X - y|] — weighted mean absolute deviation
    ea = (np.abs(scenarios - y) * probs[:, None]).sum(axis=0)  # [T]

    # E[|X - X'|] — using symmetry: E[|X - X'|] = 2 * sum_i sum_j p_i p_j |x_i - x_j| / 2
    # Efficient: E[|X - X'|] = 2 * sum_{i<j} p_i * p_j * |x_i - x_j|
    eb = np.zeros(t)
    for i in range(k):
        for j in range(i + 1, k):
            eb += 2 * probs[i] * probs[j] * np.abs(scenarios[i] - scenarios[j])

    crps_t = ea - 0.5 * eb   # [T]
    return float(crps_t.mean())


def coverage_80(
    scenarios: np.ndarray,  # [K, T]
    probs: np.ndarray,       # [K]
    realized: np.ndarray,   # [T]
) -> float:
    """Fraction of realized values inside the empirical 80% predictive interval."""
    # Compute 10th and 90th quantiles via weighted empirical distribution
    lo = _weighted_quantile(scenarios, probs, 0.10)  # [T]
    hi = _weighted_quantile(scenarios, probs, 0.90)  # [T]
    inside = (realized >= lo) & (realized <= hi)
    # Only count time steps where realized is not NaN
    valid = np.isfinite(realized)
    if not valid.any():
        return np.nan
    return float(inside[valid].mean())


def _weighted_quantile(
    scenarios: np.ndarray,  # [K, T]
    probs: np.ndarray,       # [K]
    q: float,
) -> np.ndarray:
    """Empirical quantile at level q via sorted weighted CDF, shape [T]."""
    k, t = scenarios.shape
    order = np.argsort(scenarios, axis=0)             # [K, T]
    sorted_s = np.take_along_axis(scenarios, order, axis=0)  # [K, T]
    sorted_p = probs[order]                            # [K, T]
    cdf = np.cumsum(sorted_p, axis=0)                  # [K, T]
    # First index where CDF >= q
    idx = np.argmax(cdf >= q, axis=0)                  # [T]
    return sorted_s[idx, np.arange(t)]                 # [T]


# ── Backtest runner ───────────────────────────────────────────────────────────

def run_backtest(
    panel_days: list[date],
    panel_name: str,
    forecaster: BootstrapForecaster,
) -> dict:
    """Run backtest for a list of target days.

    Returns a results dict with per-series metrics.
    """
    results: list[dict] = []

    for target_day in panel_days:
        logger.info("Backtesting %s...", target_day)

        # Generate scenario tree
        try:
            tree = forecaster.forecast(target_day)
        except Exception as e:
            logger.error("Forecast failed for %s: %s", target_day, e)
            results.append({
                "day": str(target_day),
                "error": str(e),
            })
            continue

        # Get realized RT prices for comparison
        realized_array = forecaster.dataset.get_rt_array(target_day)  # [6, 288]

        day_result: dict = {
            "day": str(target_day),
            "K": tree.n_scenarios,
            "pool_size": tree.metadata.get("pool_size"),
            "matched_count": tree.metadata.get("matched_count"),
            "day_type_relaxed": tree.metadata.get("day_type_relaxed"),
        }

        for si, series_name in enumerate(SERIES_NAMES):
            scen_s = tree.scenarios[:, si, :]   # [K, 288]
            prob_s = tree.probabilities          # [K]
            real_s = realized_array[si, :]      # [288]
            mean_s = tree.mean_trajectory()[si, :]  # [288]

            # Skip if realized data is all NaN
            if np.isnan(real_s).all():
                day_result[series_name] = {"error": "no_realized_data"}
                continue

            # Bias: probability-weighted mean − realized (per-interval, then averaged)
            valid = np.isfinite(real_s)
            bias = float((mean_s[valid] - real_s[valid]).mean())

            # CRPS
            crps = crps_ensemble(scen_s[:, valid], prob_s, real_s[valid])

            # 80% coverage
            cov80 = coverage_80(scen_s[:, valid], prob_s, real_s[valid])

            day_result[series_name] = {
                "bias": round(bias, 4),
                "crps": round(crps, 4),
                "coverage_80": round(cov80, 4),
                "realized_mean": round(float(real_s[valid].mean()), 4),
                "forecast_mean": round(float(mean_s.mean()), 4),
            }

        results.append(day_result)

    # Aggregate per-series across panel
    summary: dict[str, dict] = {}
    for series_name in SERIES_NAMES:
        biases, crps_vals, covs = [], [], []
        for r in results:
            if series_name in r and "bias" in r.get(series_name, {}):
                biases.append(r[series_name]["bias"])
                crps_vals.append(r[series_name]["crps"])
                covs.append(r[series_name]["coverage_80"])

        if biases:
            summary[series_name] = {
                "mean_bias": round(float(np.mean(biases)), 4),
                "std_bias": round(float(np.std(biases)), 4),
                "mean_crps": round(float(np.mean(crps_vals)), 4),
                "coverage_80_mean": round(float(np.mean(covs)), 4),
                "n_days": len(biases),
            }

    return {
        "panel": panel_name,
        "days": [r["day"] for r in results],
        "day_results": results,
        "summary": summary,
    }


# ── Gate check ────────────────────────────────────────────────────────────────

def run_gate(results: dict) -> tuple[bool, list[str]]:
    """Check if backtest metrics pass the W3-B quality gate."""
    issues: list[str] = []
    summary = results.get("summary", {})
    panel = results.get("panel", "?")

    BIAS_WARN = {
        "lmp": 5.0,           # $/MWh — energy prices can swing; flag > $5 systematic bias
        "mcpc_regup": 1.0,    # $/MW
        "mcpc_regdn": 1.0,
        "mcpc_rrs": 0.5,
        "mcpc_ecrs": 0.5,
        "mcpc_nspin": 1.0,
    }
    COVERAGE_WARN_LOW = 0.60  # Below 60% is seriously miscalibrated

    for series, stats in summary.items():
        bias = abs(stats.get("mean_bias", 0))
        cov = stats.get("coverage_80_mean", 1.0)
        thresh = BIAS_WARN.get(series, 1.0)

        if bias > thresh:
            issues.append(
                f"[{panel}] {series}: |bias|={bias:.3f} exceeds threshold {thresh:.1f}"
            )
        if cov < COVERAGE_WARN_LOW:
            issues.append(
                f"[{panel}] {series}: 80% coverage={cov:.1%} < {COVERAGE_WARN_LOW:.0%} threshold"
            )

    return len(issues) == 0, issues


# ── Report writer ─────────────────────────────────────────────────────────────

def write_markdown_report(
    all_results: list[dict],
    path: Path,
    gate_passed: bool,
    gate_issues: list[str],
) -> None:
    """Write a Markdown backtest report."""
    lines = [
        "# W3-B Backtest Report: Bootstrap Probabilistic Forecaster",
        "",
        f"**Gate status:** {'✓ PASSED' if gate_passed else '✗ FAILED'}",
        "",
    ]

    if gate_issues:
        lines.append("## Gate Issues")
        for issue in gate_issues:
            lines.append(f"- {issue}")
        lines.append("")

    for results in all_results:
        panel = results["panel"]
        days = results["days"]
        summary = results["summary"]

        lines.append(f"## Panel: {panel}")
        lines.append(f"Days: {', '.join(days)}")
        lines.append("")
        lines.append("### Per-Series Metrics (averaged over panel)")
        lines.append("")
        lines.append("| Series | Mean Bias | Std Bias | Mean CRPS | 80% Coverage | N Days |")
        lines.append("|--------|-----------|----------|-----------|--------------|--------|")

        for series in SERIES_NAMES:
            if series not in summary:
                continue
            s = summary[series]
            unit = "$/MWh" if series == "lmp" else "$/MW"
            lines.append(
                f"| {series} | {s['mean_bias']:+.3f} {unit} | "
                f"{s['std_bias']:.3f} | {s['mean_crps']:.3f} | "
                f"{s['coverage_80_mean']:.1%} | {s['n_days']} |"
            )

        lines.append("")
        lines.append("### Per-Day Details")
        lines.append("")

        for dr in results["day_results"]:
            day = dr["day"]
            if "error" in dr:
                lines.append(f"- **{day}**: ERROR — {dr['error']}")
                continue
            lines.append(
                f"- **{day}**: K={dr.get('K')}, pool={dr.get('pool_size')}, "
                f"matched={dr.get('matched_count')}, "
                f"relaxed={dr.get('day_type_relaxed')}"
            )
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    logger.info("Markdown report written to %s", path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="W3-B backtest runner")
    parser.add_argument(
        "--panel", choices=["primary", "secondary", "both"], default="primary",
        help="Which panel to run (default: primary=Apr 20-26)"
    )
    parser.add_argument("--start", help="Custom start date (overrides panel)")
    parser.add_argument("--end", help="Custom end date exclusive (overrides panel)")
    args = parser.parse_args()

    # ── Define panels ──────────────────────────────────────────────────────────
    panels: list[tuple[str, list[date]]] = []

    if args.start and args.end:
        custom_start = date.fromisoformat(args.start)
        custom_end = date.fromisoformat(args.end)
        days = [custom_start + timedelta(days=i) for i in range((custom_end - custom_start).days)]
        panels.append(("custom", days))
    else:
        if args.panel in ("primary", "both"):
            primary_days = [date(2026, 4, 20) + timedelta(days=i) for i in range(7)]
            panels.append(("Apr 20-26 2026 (primary)", primary_days))
        if args.panel in ("secondary", "both"):
            secondary_days = [date(2026, 2, 1) + timedelta(days=i) for i in range(7)]
            panels.append(("Feb 1-7 2026 (secondary stress)", secondary_days))

    logger.info("W3-B Backtest")
    for name, days in panels:
        logger.info("  Panel: %s (%d days)", name, len(days))

    # ── Initialize forecaster ──────────────────────────────────────────────────
    dataset = ForecasterDataset()
    forecaster = BootstrapForecaster(dataset=dataset)

    # ── Run backtests ──────────────────────────────────────────────────────────
    all_results: list[dict] = []
    for panel_name, panel_days in panels:
        logger.info("Running backtest: %s", panel_name)
        results = run_backtest(panel_days, panel_name, forecaster)
        all_results.append(results)

    # ── Gate check ─────────────────────────────────────────────────────────────
    all_passed = True
    all_issues: list[str] = []
    for results in all_results:
        passed, issues = run_gate(results)
        if not passed:
            all_passed = False
        all_issues.extend(issues)

    # ── Print summary ──────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS SUMMARY")
    logger.info("=" * 60)

    for results in all_results:
        logger.info("\n--- %s ---", results["panel"])
        for series, stats in results.get("summary", {}).items():
            logger.info(
                "  %-18s bias=%+.3f  crps=%.3f  cov80=%.1f%%",
                series,
                stats["mean_bias"],
                stats["mean_crps"],
                stats["coverage_80_mean"] * 100,
            )

    logger.info("")
    if all_issues:
        logger.error("GATE RESULT: FAILED")
        logger.error("Issues found:")
        for issue in all_issues:
            logger.error("  !! %s", issue)
        logger.error("")
        logger.error(
            "HALT: Report these metrics to chat. Do NOT tune until Karthik reviews.\n"
            "A miscalibrated forecaster is a real finding W3-C needs to know about."
        )
    else:
        logger.info("GATE RESULT: PASSED — forecaster within calibration thresholds.")

    # ── Write reports ──────────────────────────────────────────────────────────
    report_path = REPO_ROOT / "docs" / "backtest_w3b.md"
    write_markdown_report(all_results, report_path, all_passed, all_issues)

    json_path = REPO_ROOT / "data" / "audit" / "backtest_w3b.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "all_results": all_results,
                "gate_passed": all_passed,
                "gate_issues": all_issues,
            },
            indent=2,
            default=str,
        )
    )
    logger.info("JSON report written to %s", json_path)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
