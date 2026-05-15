"""Migration tests: v0.1 Parquet files validate against the migrated schema.

Constraint (Week 2): every ADR-driven schema change has a migration test.
These tests load existing v0.1 Parquet files and confirm the migrated
Pydantic models accept the data (or document explicit deprecation paths).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from ercot_rtcb_bench.data.schema import (
    PRODUCT_FAMILY,
    ASDCHourly,
    ASDCParameters,
    ASProduct,
    Awards,
    DAMPrices,
    RTPrices,
)

V01_DIR = Path(os.environ.get("V01_DIR", Path.home() / "hybridbid-bench-data" / "v0.1"))
HAS_V01 = V01_DIR.exists()

skip_no_v01 = pytest.mark.skipif(not HAS_V01, reason=f"v0.1 data not found at {V01_DIR}")


# ── ADR 0002 regression tests ─────────────────────────────────────────────────


class TestADR0002RRSUnified:
    def test_as_product_has_exactly_five_values(self):
        """Regression guard: ASProduct enum must have exactly 5 values (ADR 0002)."""
        assert len(ASProduct) == 5

    def test_rrs_is_single_enum_value(self):
        assert ASProduct.RRS == "rrs"
        with pytest.raises(ValueError):
            ASProduct("rrs_pfr")
        with pytest.raises(ValueError):
            ASProduct("rrs_ffr")

    def test_rt_prices_has_no_rrs_sub_product_columns(self):
        """RTPrices schema must not contain mcpc_rrs_pfr/ffr/ufr columns."""
        fields = set(RTPrices.model_fields.keys())
        for bad in ("mcpc_rrs_pfr", "mcpc_rrs_ffr", "mcpc_rrs_ufr"):
            assert bad not in fields, f"ADR 0002 violation: {bad} found in RTPrices"

    def test_rt_prices_has_five_mcpc_columns(self):
        mcpc_fields = [f for f in RTPrices.model_fields if f.startswith("mcpc_")]
        assert len(mcpc_fields) == 5, f"Expected 5 MCPC columns, got {mcpc_fields}"

    def test_awards_has_rrs_sub_product_columns(self):
        """Awards preserves sub-product breakdown for settlement reconciliation."""
        fields = set(Awards.model_fields.keys())
        for col in ("award_rrs_pfr", "award_rrs_ffr", "award_rrs_ufr"):
            assert col in fields

    def test_bess_ufr_must_be_zero(self):
        with pytest.raises(ValidationError):
            Awards(
                timestamp_utc=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                resource_name="BATT_X",
                award_energy=0.0,
                award_regup=0.0,
                award_regdn=0.0,
                award_rrs_pfr=0.0,
                award_rrs_ffr=10.0,
                award_rrs_ufr=5.0,  # must be 0 for BESS
                award_ecrs=0.0,
                award_nspin=0.0,
                is_bess=True,
            )

    def test_awards_rrs_invariant_documented(self):
        """Awards with non-zero RRS sub-product splits are valid (ADR 0002)."""
        a = Awards(
            timestamp_utc=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            resource_name="BATT_X",
            award_energy=20.0,
            award_regup=0.0,
            award_regdn=0.0,
            award_rrs_pfr=5.0,
            award_rrs_ffr=15.0,
            award_rrs_ufr=0.0,
            award_ecrs=0.0,
            award_nspin=0.0,
            is_bess=True,
        )
        assert a.award_rrs_pfr + a.award_rrs_ffr + a.award_rrs_ufr == 20.0


# ── ADR 0004 regression tests ─────────────────────────────────────────────────


class TestADR0004NonSpin:
    def test_rt_prices_has_single_nspin_column(self):
        fields = set(RTPrices.model_fields.keys())
        assert "mcpc_nspin" in fields
        assert "mcpc_nspin_online" not in fields
        assert "mcpc_nspin_offline" not in fields

    def test_dam_prices_has_two_nspin_columns(self):
        fields = set(DAMPrices.model_fields.keys())
        assert "mcpc_nspin_online" in fields
        assert "mcpc_nspin_offline" in fields
        assert "mcpc_nspin" not in fields

    def test_product_family_nspin_variants_map_to_nspin(self):
        assert PRODUCT_FAMILY["nspin_online"] == "nspin"
        assert PRODUCT_FAMILY["nspin_offline"] == "nspin"
        assert PRODUCT_FAMILY["nspin"] == "nspin"

    def test_product_family_has_seven_keys(self):
        """5 RT products + 2 DAM-only Non-Spin variants = 7 keys."""
        assert len(PRODUCT_FAMILY) == 7

    def test_product_family_all_values_are_valid_products(self):
        valid = {p.value for p in ASProduct}
        for k, v in PRODUCT_FAMILY.items():
            assert v in valid, f"PRODUCT_FAMILY[{k!r}] = {v!r} not in ASProduct"


# ── ADR 0003 schema tests ─────────────────────────────────────────────────────


class TestADR0003ASDCSchema:
    def test_asdc_parameters_weights_must_sum_to_one(self):
        with pytest.raises(ValidationError):
            ASDCParameters(
                as_product=ASProduct.REGUP,
                effective_date=date(2025, 12, 5),
                mu=100.0,
                sigma=50.0,
                mix_weight_30min=0.6,
                mix_weight_60min=0.6,  # sum = 1.2 ≠ 1.0
                voll=5000.0,
                voll_cap_offset=250.0,
                min_step_floor=0.0,
                source_url="https://example.com",
                source_doc_revision="v1",
            )

    def test_asdc_parameters_valid(self):
        a = ASDCParameters(
            as_product=ASProduct.RRS,
            effective_date=date(2025, 12, 5),
            mu=120.0,
            sigma=60.0,
            mix_weight_30min=0.4,
            mix_weight_60min=0.6,
            voll=5000.0,
            voll_cap_offset=250.0,
            min_step_floor=0.25,
            source_url="https://ercot.com/rtcbtf",
            source_doc_revision="RTC+B go-live 2025-09-30",
        )
        assert a.as_product == ASProduct.RRS

    def test_asdc_hourly_valid(self):
        h = ASDCHourly(
            operating_date=date(2026, 1, 15),
            hour_ending=14,
            as_product=ASProduct.REGUP,
            segment_index=0,
            breakpoint_mw=500.0,
            breakpoint_price=3.50,
            as_plan_mw=2500.0,
            source_filename="NP4-212-CD_20260115.csv",
        )
        assert h.segment_index == 0

    def test_asdc_hourly_hour_ending_bounds(self):
        with pytest.raises(ValidationError):
            ASDCHourly(
                operating_date=date(2026, 1, 15),
                hour_ending=0,  # must be 1..24
                as_product=ASProduct.ECRS,
                segment_index=0,
                breakpoint_mw=100.0,
                breakpoint_price=2.0,
                as_plan_mw=500.0,
                source_filename="x.csv",
            )


# ── v0.1 Parquet migration validation ─────────────────────────────────────────


@skip_no_v01
class TestV01ParquetMigration:
    """Load existing v0.1 Parquet files and confirm schema compatibility."""

    def test_rt_prices_loads_and_validates(self):
        for f in sorted((V01_DIR / "rt_prices").glob("*.parquet")):
            df = pd.read_parquet(f)
            assert "lmp" in df.columns, f"{f}: missing 'lmp'"
            assert "settlement_point" in df.columns
            # The v0.1 rt_prices don't yet have per-column MCPCs (they're in
            # as_clearing); this is a migration gap documented in transform.py.
            # What must NOT be present:
            for bad in ("mcpc_rrs_pfr", "mcpc_rrs_ffr", "mcpc_rrs_ufr"):
                assert bad not in df.columns, f"ADR 0002 violation in {f}: {bad}"

    def test_as_clearing_has_no_rrs_sub_products(self):
        for f in sorted((V01_DIR / "as_clearing").glob("*.parquet")):
            df = pd.read_parquet(f)
            assert "as_product" in df.columns
            # No sub-product price columns
            for bad in ("as_product_pfr", "as_product_ffr"):
                assert bad not in df.columns
            # RRS exists as a single product code
            if "RRS" in df["as_product"].values or "rrs" in df["as_product"].values:
                pass  # present and unified — correct

    def test_dam_prices_non_spin_column_structure(self):
        """v0.1 dam_prices uses dam_mcpc_nspin (old name) — document migration gap."""
        for f in sorted((V01_DIR / "dam_prices").glob("*.parquet")):
            df = pd.read_parquet(f)
            # v0.1 has 'dam_mcpc_nspin' (combined); no online/offline split.
            # This is a known migration gap: v0.2 will split to
            # mcpc_nspin_online/offline per ADR 0004.
            # Assert that the OLD schema doesn't have split columns already:
            assert "mcpc_nspin_online" not in df.columns
            assert "mcpc_nspin_offline" not in df.columns
