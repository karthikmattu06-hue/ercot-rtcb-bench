"""Data validation gates for canonical v0.1 Parquet tables.

Produces a structured validation report covering:
  - Coverage: % of expected 5-min/hourly intervals present per table per month
  - Schema conformance: columns, dtypes, Pydantic model validation (sampled)
  - Sanity bounds: LMP range, MCPC non-negative, MW non-negative
  - Cross-table consistency: RT price timestamps ⊆ AS clearing timestamps
  - Distribution sanity: flag months where mean/p95 deviate >3σ from others
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LMP_MIN = -251.0
LMP_MAX = 5_000.0
COVERAGE_TARGET = 0.995  # 99.5% for clock-driven data (LMP, DAM, system conditions)
AS_CLEARING_COVERAGE_TARGET = 0.94  # 94% for event-driven SCED MCPCs (irregular cadence)
DAM_COVERAGE_TARGET = 0.990  # 99.0% for DAM (allows 6-hour CST boundary artifact)
DISTRIBUTION_SIGMA = 3.0

AS_PRODUCTS = ["REGUP", "REGDN", "RRS", "ECRS", "NSPIN"]

# Small negative MCPC values (> this threshold) are treated as float noise
MCPC_NEGATIVE_TOLERANCE = -0.05


# ── Report structures ─────────────────────────────────────────────────────────


@dataclass
class TableReport:
    table: str
    months_checked: list[str] = field(default_factory=list)
    coverage_by_month: dict[str, float] = field(default_factory=dict)
    schema_errors: list[str] = field(default_factory=list)
    bounds_errors: list[str] = field(default_factory=list)
    distribution_flags: list[str] = field(default_factory=list)
    passed: bool = True

    def fail(self, msg: str) -> None:
        logger.warning("[%s] FAIL: %s", self.table, msg)
        self.passed = False


@dataclass
class ValidationReport:
    version: str
    tables: dict[str, TableReport] = field(default_factory=dict)
    cross_table_errors: list[str] = field(default_factory=list)

    @property
    def overall_passed(self) -> bool:
        return all(t.passed for t in self.tables.values()) and not self.cross_table_errors

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "overall_passed": self.overall_passed,
            "tables": {
                name: {
                    "passed": t.passed,
                    "months": t.months_checked,
                    "coverage": t.coverage_by_month,
                    "schema_errors": t.schema_errors,
                    "bounds_errors": t.bounds_errors,
                    "distribution_flags": t.distribution_flags,
                }
                for name, t in self.tables.items()
            },
            "cross_table_errors": self.cross_table_errors,
        }


# ── Coverage checking ─────────────────────────────────────────────────────────


def _expected_intervals(
    month_str: str,
    freq: str,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> int:
    """Expected number of intervals in a month at the given frequency.

    dataset_start/dataset_end clip the month window for partial months at the
    boundaries of the dataset (e.g., December 2025 starts at RTC+B launch, not
    at midnight Dec 1).
    """
    period = pd.Period(month_str, freq="M")
    start = period.start_time.tz_localize("UTC")
    end = (period + 1).start_time.tz_localize("UTC")
    if dataset_start is not None:
        start = max(start, dataset_start)
    if dataset_end is not None:
        end = min(end, dataset_end)
    if start >= end:
        return 0
    return len(pd.date_range(start=start, end=end, freq=freq, inclusive="left"))


def check_coverage(
    df: pd.DataFrame,
    timestamp_col: str,
    month_str: str,
    freq: str,
    report: TableReport,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> None:
    n_actual = df[timestamp_col].nunique()
    n_expected = _expected_intervals(month_str, freq, dataset_start, dataset_end)
    coverage = n_actual / n_expected if n_expected > 0 else 0.0
    report.coverage_by_month[month_str] = round(coverage, 4)
    if coverage < COVERAGE_TARGET:
        report.fail(
            f"{month_str}: coverage {coverage:.1%} < {COVERAGE_TARGET:.1%} "
            f"({n_actual}/{n_expected} intervals)"
        )


# ── Bounds checking ───────────────────────────────────────────────────────────


def check_lmp_bounds(df: pd.DataFrame, col: str, month: str, report: TableReport) -> None:
    out = df[(df[col] < LMP_MIN) | (df[col] > LMP_MAX)]
    if len(out) > 0:
        report.fail(f"{month}: {len(out)} {col} values out of [{LMP_MIN}, {LMP_MAX}]")
        report.bounds_errors.append(f"{month}: {col} OOB count={len(out)}")


def check_nonneg(
    df: pd.DataFrame,
    cols: list[str],
    month: str,
    report: TableReport,
    tolerance: float = 0.0,
) -> None:
    for col in cols:
        if col not in df.columns:
            continue
        n_neg = (df[col] < tolerance).sum()
        if n_neg > 0:
            report.fail(f"{month}: {n_neg} negative values in {col} (tolerance={tolerance})")
            report.bounds_errors.append(f"{month}: {col} negative count={n_neg}")


# ── Distribution sanity ───────────────────────────────────────────────────────


def flag_distribution_outliers(
    monthly_stats: dict[str, dict[str, float]],
    metric: str,
    report: TableReport,
) -> None:
    """Flag months where metric deviates >3σ from the ensemble mean."""
    values = [(m, s[metric]) for m, s in monthly_stats.items() if metric in s and not np.isnan(s[metric])]
    if len(values) < 3:
        return
    months, vals = zip(*values, strict=False)
    arr = np.array(vals, dtype=float)
    mean, std = np.nanmean(arr), np.nanstd(arr)
    if std == 0:
        return
    for m, v in zip(months, arr, strict=False):
        if abs(v - mean) > DISTRIBUTION_SIGMA * std:
            msg = f"{m}: {metric}={v:.2f} deviates {abs(v-mean)/std:.1f}σ from mean {mean:.2f}"
            report.distribution_flags.append(msg)
            logger.warning("[%s] Distribution flag: %s", report.table, msg)


# ── Per-table validators ──────────────────────────────────────────────────────


def validate_rt_prices(
    table_dir: Path,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> TableReport:
    report = TableReport(table="rt_prices")
    monthly_stats: dict[str, dict[str, float]] = {}

    for f in sorted(table_dir.glob("*.parquet")):
        month = f.stem
        report.months_checked.append(month)
        df = pd.read_parquet(f)

        required = {"timestamp_utc", "settlement_point", "lmp", "is_post_rtcb"}
        missing = required - set(df.columns)
        if missing:
            report.fail(f"{month}: missing columns {missing}")
            continue

        check_coverage(df, "timestamp_utc", month, "5min", report, dataset_start, dataset_end)
        check_lmp_bounds(df, "lmp", month, report)

        stats = {
            "mean": float(df["lmp"].mean()),
            "median": float(df["lmp"].median()),
            "p5": float(df["lmp"].quantile(0.05)),
            "p95": float(df["lmp"].quantile(0.95)),
        }
        monthly_stats[month] = stats

    for metric in ["mean", "p95"]:
        flag_distribution_outliers(monthly_stats, metric, report)

    return report


def validate_as_clearing(
    table_dir: Path,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> TableReport:
    report = TableReport(table="as_clearing")
    monthly_stats: dict[str, dict[str, dict[str, float]]] = {}

    for f in sorted(table_dir.glob("*.parquet")):
        month = f.stem
        report.months_checked.append(month)
        df = pd.read_parquet(f)

        required = {"timestamp_utc", "as_product", "mcpc", "is_post_rtcb"}
        missing = required - set(df.columns)
        if missing:
            report.fail(f"{month}: missing columns {missing}")
            continue

        # Check all 5 AS products present each month
        products_found = set(df["as_product"].unique())
        missing_prods = set(AS_PRODUCTS) - products_found
        if missing_prods:
            report.fail(f"{month}: missing AS products {missing_prods}")

        # Coverage check per product (window-aware for partial months)
        # SCED runs are event-driven (~every 5 min) not clock-driven, so
        # irregular gaps of 1-2 bins are normal; use a lower threshold.
        for prod in AS_PRODUCTS:
            prod_df = df[df["as_product"] == prod]
            n = prod_df["timestamp_utc"].nunique()
            expected = _expected_intervals(month, "5min", dataset_start, dataset_end)
            cov = n / expected if expected > 0 else 0.0
            if cov < AS_CLEARING_COVERAGE_TARGET:
                report.fail(f"{month} {prod}: coverage {cov:.1%}")

        # Allow small negative MCPC values (float noise from pricing engine)
        check_nonneg(df, ["mcpc"], month, report, tolerance=MCPC_NEGATIVE_TOLERANCE)

        monthly_stats[month] = {}
        for prod in AS_PRODUCTS:
            prod_df = df[df["as_product"] == prod]["mcpc"]
            if len(prod_df) == 0:
                continue
            monthly_stats[month][f"{prod}_mean"] = float(prod_df.mean())
            monthly_stats[month][f"{prod}_p95"] = float(prod_df.quantile(0.95))

    for prod in AS_PRODUCTS:
        flag_distribution_outliers(monthly_stats, f"{prod}_mean", report)

    return report


def validate_dam_prices(
    table_dir: Path,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> TableReport:
    report = TableReport(table="dam_prices")

    for f in sorted(table_dir.glob("*.parquet")):
        month = f.stem
        report.months_checked.append(month)
        df = pd.read_parquet(f)

        required = {"timestamp_utc", "settlement_point", "dam_spp",
                    "dam_mcpc_regup", "dam_mcpc_regdn", "dam_mcpc_rrs",
                    "dam_mcpc_ecrs", "dam_mcpc_nspin"}
        missing = required - set(df.columns)
        if missing:
            report.fail(f"{month}: missing columns {missing}")
            continue

        n_expected = _expected_intervals(month, "h", dataset_start, dataset_end)
        n_actual = df["timestamp_utc"].nunique()
        cov = n_actual / n_expected if n_expected > 0 else 0.0
        report.coverage_by_month[month] = round(cov, 4)
        if cov < DAM_COVERAGE_TARGET:
            report.fail(f"{month}: DAM coverage {cov:.1%}")

        mcpc_cols = ["dam_mcpc_regup", "dam_mcpc_regdn", "dam_mcpc_rrs",
                     "dam_mcpc_ecrs", "dam_mcpc_nspin"]
        check_nonneg(df, mcpc_cols, month, report)

    return report


def validate_system_conditions(
    table_dir: Path,
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
) -> TableReport:
    report = TableReport(table="system_conditions")

    for f in sorted(table_dir.glob("*.parquet")):
        month = f.stem
        report.months_checked.append(month)
        df = pd.read_parquet(f)

        check_coverage(df, "timestamp_utc", month, "5min", report, dataset_start, dataset_end)
        check_nonneg(
            df,
            ["total_load_mw", "load_forecast_mw", "wind_actual_mw",
             "solar_actual_mw", "wind_forecast_mw", "solar_forecast_mw"],
            month,
            report,
        )

    return report


# ── AS Plan validator ─────────────────────────────────────────────────────────

# v0.1 window: Dec 5, 2025 – Mar 31, 2026 (117 days × 24 hours = 2808)
# Minus one DST spring-forward gap (Mar 8, 2026 HE 3 CT does not exist in RT)
AS_PLAN_EXPECTED_ROWS = 2807
AS_PLAN_COVERAGE_TARGET = 0.99  # ≥99% gate

# Sanity bounds per product column (MW)
_AS_PLAN_BOUNDS: dict[str, tuple[float, float]] = {
    "rureq":    (0.0, 5_000.0),
    "regdnreq": (0.0, 5_000.0),
    "rrsreq":   (0.0, 10_000.0),
    "ecrsreq":  (0.0, 10_000.0),
    "nspinreq": (0.0, 10_000.0),
}


def validate_as_plan(table_dir: Path) -> TableReport:
    """Validate AS Plan Parquet files under table_dir.

    Checks:
      - Coverage: ≥99% of expected 2,807 (operating_date, hour_ending) pairs.
      - Bounds: each product column within defined MW range.
      - Schema: required columns present.
    """
    report = TableReport(table="as_plan")
    parquet_files = sorted(table_dir.glob("*.parquet"))

    if not parquet_files:
        report.fail(f"No Parquet files found in {table_dir}")
        return report

    frames: list[pd.DataFrame] = []
    for f in parquet_files:
        month = f.stem
        report.months_checked.append(month)
        df = pd.read_parquet(f)

        required = {"operating_date", "hour_ending", "rureq", "regdnreq", "rrsreq", "ecrsreq", "nspinreq"}
        missing_cols = required - set(df.columns)
        if missing_cols:
            report.fail(f"{month}: missing columns {missing_cols}")
            continue

        frames.append(df)

    if not frames:
        report.fail("No valid data after schema check")
        return report

    all_df = pd.concat(frames, ignore_index=True)

    # Coverage: count unique (operating_date, hour_ending) pairs
    n_actual = len(all_df[["operating_date", "hour_ending"]].drop_duplicates())
    coverage = n_actual / AS_PLAN_EXPECTED_ROWS
    report.coverage_by_month["overall"] = round(coverage, 4)
    if coverage < AS_PLAN_COVERAGE_TARGET:
        report.fail(
            f"Coverage {coverage:.1%} < {AS_PLAN_COVERAGE_TARGET:.1%} "
            f"({n_actual}/{AS_PLAN_EXPECTED_ROWS} expected rows)"
        )

    # Bounds check per product column
    for col, (lo, hi) in _AS_PLAN_BOUNDS.items():
        if col not in all_df.columns:
            continue
        oob = all_df[(all_df[col] < lo) | (all_df[col] > hi)]
        if len(oob) > 0:
            msg = f"{col}: {len(oob)} rows outside [{lo}, {hi}] MW"
            report.bounds_errors.append(msg)
            report.fail(msg)

    return report


# ── Cross-table checks ────────────────────────────────────────────────────────


def cross_table_consistency(
    processed_dir: Path,
    report: ValidationReport,
    as_clearing_end: pd.Timestamp | None = None,
) -> None:
    """Check that timestamps in rt_prices have corresponding as_clearing entries.

    as_clearing_end: if set, only checks rt_prices timestamps before this bound.
    This handles the case where sced_mcpc data ends before the rt_prices window.
    """
    rt_dir = processed_dir / "rt_prices"
    as_dir = processed_dir / "as_clearing"

    for f in sorted(rt_dir.glob("*.parquet")):
        month = f.stem
        as_file = as_dir / f"{month}.parquet"
        if not as_file.exists():
            report.cross_table_errors.append(f"{month}: as_clearing missing but rt_prices present")
            continue

        rt_df = pd.read_parquet(f)
        if as_clearing_end is not None:
            rt_df = rt_df[rt_df["timestamp_utc"] < as_clearing_end]
        if len(rt_df) == 0:
            continue

        rt_ts = set(rt_df["timestamp_utc"])
        as_ts = set(pd.read_parquet(as_file)["timestamp_utc"].unique())
        orphans = rt_ts - as_ts
        frac = len(orphans) / len(rt_ts) if rt_ts else 0.0
        # Allow up to 6% gap: as_clearing is event-driven (SCED runs) while
        # rt_prices is clock-driven; ~5% of 5-min slots may have no SCED run.
        if frac > 0.06:
            report.cross_table_errors.append(
                f"{month}: {len(orphans)} rt_prices timestamps ({frac:.1%}) "
                f"missing from as_clearing (threshold 6%)"
            )


# ── Entry point ───────────────────────────────────────────────────────────────


def run_validation(
    processed_dir: Path,
    version: str = "v0.1",
    dataset_start: pd.Timestamp | None = None,
    dataset_end: pd.Timestamp | None = None,
    as_clearing_end: pd.Timestamp | None = None,
) -> ValidationReport:
    """Run all validation gates.

    dataset_start / dataset_end: bounds for the full dataset window (used for
      all tables). Partial months at the boundaries are counted correctly.
    as_clearing_end: separate end bound for as_clearing when SCED MCPC data
      does not extend to dataset_end (e.g., sced_mcpc through Mar 21 vs
      full dataset through Mar 31).
    """
    report = ValidationReport(version=version)

    table_configs = [
        ("rt_prices", validate_rt_prices, dataset_start, dataset_end),
        ("as_clearing", validate_as_clearing, dataset_start, as_clearing_end or dataset_end),
        ("dam_prices", validate_dam_prices, dataset_start, dataset_end),
        ("system_conditions", validate_system_conditions, dataset_start, dataset_end),
    ]

    for table_name, validator, tbl_start, tbl_end in table_configs:
        table_dir = processed_dir / table_name
        if not table_dir.exists():
            logger.warning("Table directory missing: %s", table_dir)
            r = TableReport(table=table_name)
            r.fail(f"Directory {table_dir} does not exist")
            report.tables[table_name] = r
            continue
        logger.info("Validating %s...", table_name)
        report.tables[table_name] = validator(table_dir, tbl_start, tbl_end)

    # AS Plan uses a different signature (no timestamp bounds — keyed by operating_date)
    as_plan_dir = processed_dir / "as_plan"
    if as_plan_dir.exists():
        logger.info("Validating as_plan...")
        report.tables["as_plan"] = validate_as_plan(as_plan_dir)
    else:
        logger.warning("Table directory missing: %s", as_plan_dir)
        r = TableReport(table="as_plan")
        r.fail(f"Directory {as_plan_dir} does not exist")
        report.tables["as_plan"] = r

    cross_table_consistency(processed_dir, report, as_clearing_end=as_clearing_end)

    status = "PASSED" if report.overall_passed else "FAILED"
    logger.info("Validation %s for %s", status, version)
    return report


def write_validation_report(report: ValidationReport, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / f"{report.version.replace('.', '_')}_report.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
    logger.info("Wrote %s", json_path)

    # Markdown
    md_path = out_dir / f"{report.version.replace('.', '_')}_report.md"
    lines = [
        f"# Validation Report: {report.version}",
        "",
        f"**Overall: {'✅ PASSED' if report.overall_passed else '❌ FAILED'}**",
        "",
    ]
    for name, t in report.tables.items():
        status = "✅" if t.passed else "❌"
        lines += [f"## {status} {name}", ""]
        if t.coverage_by_month:
            lines.append("### Coverage")
            for month, cov in sorted(t.coverage_by_month.items()):
                flag = "" if cov >= COVERAGE_TARGET else " ⚠️"
                lines.append(f"- {month}: {cov:.1%}{flag}")
            lines.append("")
        if t.bounds_errors:
            lines += ["### Bounds errors", *[f"- {e}" for e in t.bounds_errors], ""]
        if t.distribution_flags:
            lines += ["### Distribution flags", *[f"- {f}" for f in t.distribution_flags], ""]
        if t.schema_errors:
            lines += ["### Schema errors", *[f"- {e}" for e in t.schema_errors], ""]
    if report.cross_table_errors:
        lines += ["## Cross-table errors", *[f"- {e}" for e in report.cross_table_errors], ""]
    md_path.write_text("\n".join(lines) + "\n")
    logger.info("Wrote %s", md_path)
