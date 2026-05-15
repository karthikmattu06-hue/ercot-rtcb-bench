"""Tests for the validation module (unit tests with synthetic data)."""

from __future__ import annotations

import pandas as pd

from ercot_rtcb_bench.data.validate import (
    TableReport,
    ValidationReport,
    check_coverage,
    check_lmp_bounds,
    check_nonneg,
    validate_as_clearing,
    validate_rt_prices,
)


def make_5min_index(month: str, tz: str = "UTC") -> pd.DatetimeIndex:
    period = pd.Period(month, freq="M")
    return pd.date_range(
        start=period.start_time.tz_localize(tz),
        end=(period + 1).start_time.tz_localize(tz),
        freq="5min",
        inclusive="left",
    )


class TestCoverageCheck:
    def test_full_coverage_passes(self):
        idx = make_5min_index("2026-01")
        df = pd.DataFrame({"timestamp_utc": idx})
        report = TableReport(table="test")
        check_coverage(df, "timestamp_utc", "2026-01", "5min", report)
        assert report.passed
        assert report.coverage_by_month["2026-01"] == 1.0

    def test_partial_coverage_fails(self):
        idx = make_5min_index("2026-01")[:100]  # only first 100 intervals
        df = pd.DataFrame({"timestamp_utc": idx})
        report = TableReport(table="test")
        check_coverage(df, "timestamp_utc", "2026-01", "5min", report)
        assert not report.passed


class TestBoundsChecks:
    def test_lmp_in_bounds_passes(self):
        df = pd.DataFrame({"lmp": [0.0, 100.0, -50.0, 5000.0, -251.0]})
        report = TableReport(table="test")
        check_lmp_bounds(df, "lmp", "2026-01", report)
        assert report.passed

    def test_lmp_above_cap_fails(self):
        df = pd.DataFrame({"lmp": [5001.0]})
        report = TableReport(table="test")
        check_lmp_bounds(df, "lmp", "2026-01", report)
        assert not report.passed

    def test_nonneg_passes(self):
        df = pd.DataFrame({"mcpc": [0.0, 1.5, 100.0]})
        report = TableReport(table="test")
        check_nonneg(df, ["mcpc"], "2026-01", report)
        assert report.passed

    def test_nonneg_fails_on_negative(self):
        df = pd.DataFrame({"mcpc": [0.0, -0.01, 1.0]})
        report = TableReport(table="test")
        check_nonneg(df, ["mcpc"], "2026-01", report)
        assert not report.passed


class TestValidationReport:
    def test_to_dict_structure(self):
        report = ValidationReport(version="v0.1")
        t = TableReport(table="rt_prices")
        t.coverage_by_month["2026-01"] = 0.999
        report.tables["rt_prices"] = t
        d = report.to_dict()
        assert d["version"] == "v0.1"
        assert "rt_prices" in d["tables"]
        assert d["tables"]["rt_prices"]["coverage"]["2026-01"] == 0.999

    def test_overall_passed_false_if_table_fails(self):
        report = ValidationReport(version="v0.1")
        t = TableReport(table="rt_prices")
        t.fail("test failure")
        report.tables["rt_prices"] = t
        assert not report.overall_passed

    def test_overall_passed_false_if_cross_table_error(self):
        report = ValidationReport(version="v0.1")
        t = TableReport(table="rt_prices")
        report.tables["rt_prices"] = t
        report.cross_table_errors.append("some cross-table error")
        assert not report.overall_passed


class TestValidateRTPricesIntegration:
    def test_valid_parquet(self, tmp_path):
        idx = make_5min_index("2026-01")
        df = pd.DataFrame(
            {
                "timestamp_utc": idx,
                "settlement_point": "HB_HUBAVG",
                "settlement_point_type": "Trading Hub",
                "lmp": 45.0,
                "is_post_rtcb": True,
            }
        )
        df.to_parquet(tmp_path / "2026-01.parquet", index=False)
        report = validate_rt_prices(tmp_path)
        assert report.passed, f"Validation failed: {report.bounds_errors}"

    def test_lmp_out_of_bounds_flagged(self, tmp_path):
        idx = make_5min_index("2026-01")
        df = pd.DataFrame(
            {
                "timestamp_utc": idx,
                "settlement_point": "HB_HUBAVG",
                "settlement_point_type": "Trading Hub",
                "lmp": 6000.0,  # above cap
                "is_post_rtcb": True,
            }
        )
        df.to_parquet(tmp_path / "2026-01.parquet", index=False)
        report = validate_rt_prices(tmp_path)
        assert not report.passed


class TestValidateASClearingIntegration:
    def test_valid_parquet(self, tmp_path):
        idx = make_5min_index("2026-01")
        products = ["REGUP", "REGDN", "RRS", "ECRS", "NSPIN"]
        frames = []
        for prod in products:
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp_utc": idx,
                        "as_product": prod,
                        "mcpc": 0.5,
                        "is_post_rtcb": True,
                    }
                )
            )
        pd.concat(frames).to_parquet(tmp_path / "2026-01.parquet", index=False)
        report = validate_as_clearing(tmp_path)
        assert report.passed, f"Validation failed: {report.bounds_errors}"

    def test_missing_product_flagged(self, tmp_path):
        idx = make_5min_index("2026-01")
        # Only 4 products, missing NSPIN
        products = ["REGUP", "REGDN", "RRS", "ECRS"]
        frames = []
        for prod in products:
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp_utc": idx,
                        "as_product": prod,
                        "mcpc": 0.5,
                        "is_post_rtcb": True,
                    }
                )
            )
        pd.concat(frames).to_parquet(tmp_path / "2026-01.parquet", index=False)
        report = validate_as_clearing(tmp_path)
        assert not report.passed
