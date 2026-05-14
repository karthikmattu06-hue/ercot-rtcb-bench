"""Tests for canonical Pydantic schemas (post-ADR-0002/0003/0004 migration)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ercot_rtcb_bench.data.schema import (
    ASClearing,
    ASProduct,
    ASDCParameters,
    ASDCSegment,
    Awards,
    BESSMetadata,
    DAMPrices,
    RTPrices,
    SettlementPointType,
    SystemConditions,
)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _rt_prices(**kwargs):
    defaults = dict(
        timestamp_utc=utc(2026, 1, 15, 12, 0),
        settlement_point="HB_HUBAVG",
        settlement_point_type=SettlementPointType.TRADING_HUB,
        lmp=45.0,
        mcpc_regup=1.5,
        mcpc_regdn=0.7,
        mcpc_rrs=0.3,
        mcpc_ecrs=0.2,
        mcpc_nspin=1.0,
    )
    defaults.update(kwargs)
    return RTPrices(**defaults)


class TestRTPrices:
    def test_valid_with_all_mcpcs(self):
        r = _rt_prices()
        assert r.lmp == 45.0
        assert r.mcpc_rrs == 0.3
        assert r.mcpc_nspin == 1.0

    def test_lmp_at_offer_cap(self):
        r = _rt_prices(lmp=5000.0)
        assert r.lmp == 5000.0

    def test_negative_lmp_within_bounds(self):
        r = _rt_prices(lmp=-100.0)
        assert r.lmp == -100.0

    def test_lmp_above_cap_rejected(self):
        with pytest.raises(Exception):
            _rt_prices(lmp=5001.0)

    def test_non_utc_timestamp_rejected(self):
        import pytz
        cst = pytz.timezone("US/Central")
        ts = cst.localize(datetime(2026, 1, 15, 6, 0))
        with pytest.raises(Exception):
            _rt_prices(timestamp_utc=ts)

    def test_non_five_min_aligned_rejected(self):
        with pytest.raises(Exception):
            _rt_prices(timestamp_utc=utc(2026, 1, 15, 12, 3))

    def test_negative_mcpc_rejected(self):
        with pytest.raises(Exception):
            _rt_prices(mcpc_rrs=-0.1)


class TestASClearing:
    def test_valid_all_products(self):
        for product in ASProduct:
            r = ASClearing(
                timestamp_utc=utc(2026, 1, 15, 12, 0),
                as_product=product,
                mcpc=0.5,
            )
            assert r.as_product == product

    def test_zero_mcpc_valid(self):
        r = ASClearing(
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            as_product=ASProduct.REGUP,
            mcpc=0.0,
        )
        assert r.mcpc == 0.0

    def test_negative_mcpc_rejected(self):
        with pytest.raises(Exception):
            ASClearing(
                timestamp_utc=utc(2026, 1, 15, 12, 0),
                as_product=ASProduct.RRS,
                mcpc=-0.01,
            )


class TestDAMPrices:
    def test_non_hour_aligned_rejected(self):
        with pytest.raises(Exception):
            DAMPrices(
                timestamp_utc=utc(2026, 1, 15, 12, 30),
                settlement_point="HB_HUBAVG",
                dam_spp=45.0,
                mcpc_regup=1.0,
                mcpc_regdn=0.5,
                mcpc_rrs=0.2,
                mcpc_ecrs=0.1,
                mcpc_nspin_online=0.8,
                mcpc_nspin_offline=0.6,
            )

    def test_valid_with_nspin_split(self):
        r = DAMPrices(
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            settlement_point="HB_HUBAVG",
            dam_spp=48.0,
            mcpc_regup=1.5,
            mcpc_regdn=0.7,
            mcpc_rrs=0.3,
            mcpc_ecrs=0.2,
            mcpc_nspin_online=1.0,
            mcpc_nspin_offline=0.5,
        )
        assert r.mcpc_nspin_online == 1.0
        assert r.mcpc_nspin_offline == 0.5


class TestSystemConditions:
    def test_valid(self):
        r = SystemConditions(
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            total_load_mw=50000.0,
            load_forecast_mw=49500.0,
            wind_actual_mw=5000.0,
            wind_forecast_mw=5200.0,
            solar_actual_mw=3000.0,
            solar_forecast_mw=3100.0,
            net_load_mw=42000.0,
        )
        assert r.total_load_mw == 50000.0

    def test_net_load_inconsistency_rejected(self):
        with pytest.raises(Exception):
            SystemConditions(
                timestamp_utc=utc(2026, 1, 15, 12, 0),
                total_load_mw=50000.0,
                load_forecast_mw=49500.0,
                wind_actual_mw=5000.0,
                wind_forecast_mw=5200.0,
                solar_actual_mw=3000.0,
                solar_forecast_mw=3100.0,
                net_load_mw=99999.0,
            )


class TestBESSMetadata:
    def test_valid(self):
        b = BESSMetadata(
            resource_name="BATT_SOUTH_100",
            settlement_point="LZ_SOUTH",
            power_mw=100.0,
            energy_mwh=400.0,
            round_trip_efficiency=0.88,
            duration_hours=4.0,
        )
        assert b.duration_hours == 4.0

    def test_duration_inconsistency_rejected(self):
        with pytest.raises(Exception):
            BESSMetadata(
                resource_name="BATT_SOUTH_100",
                settlement_point="LZ_SOUTH",
                power_mw=100.0,
                energy_mwh=400.0,
                round_trip_efficiency=0.88,
                duration_hours=2.0,  # should be 4.0
            )

    def test_rte_above_one_rejected(self):
        with pytest.raises(Exception):
            BESSMetadata(
                resource_name="BATT_X",
                settlement_point="HB_HUBAVG",
                power_mw=50.0,
                energy_mwh=200.0,
                round_trip_efficiency=1.1,
                duration_hours=4.0,
            )


class TestASDCParameters:
    def test_valid(self):
        a = ASDCParameters(
            as_product=ASProduct.REGUP,
            effective_date=date(2025, 12, 5),
            mu=100.0,
            sigma=50.0,
            mix_weight_30min=0.4,
            mix_weight_60min=0.6,
            voll=5000.0,
            voll_cap_offset=250.0,
            min_step_floor=0.25,
            source_url="https://ercot.com",
            source_doc_revision="v1",
        )
        assert a.as_product == ASProduct.REGUP

    def test_weights_must_sum_to_one(self):
        with pytest.raises(Exception):
            ASDCParameters(
                as_product=ASProduct.REGUP,
                effective_date=date(2025, 12, 5),
                mu=100.0,
                sigma=50.0,
                mix_weight_30min=0.7,
                mix_weight_60min=0.6,  # 1.3 ≠ 1.0
                voll=5000.0,
                voll_cap_offset=250.0,
                min_step_floor=0.25,
                source_url="https://ercot.com",
                source_doc_revision="v1",
            )
