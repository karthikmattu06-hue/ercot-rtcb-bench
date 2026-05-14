"""Tests for canonical Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ercot_rtcb_bench.data.schema import (
    ASClearing,
    ASProduct,
    ASDCParameters,
    ASDCSegment,
    BESSMetadata,
    DAMPrices,
    RTPrices,
    SettlementPointType,
    SystemConditions,
)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestRTPrices:
    def test_valid(self):
        r = RTPrices(
            timestamp_utc=utc(2026, 1, 15, 12, 5),
            settlement_point="HB_HUBAVG",
            settlement_point_type=SettlementPointType.TRADING_HUB,
            lmp=45.23,
        )
        assert r.lmp == 45.23

    def test_lmp_at_offer_cap(self):
        r = RTPrices(
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            settlement_point="HB_NORTH",
            settlement_point_type=SettlementPointType.TRADING_HUB,
            lmp=5000.0,
        )
        assert r.lmp == 5000.0

    def test_negative_lmp_within_bounds(self):
        r = RTPrices(
            timestamp_utc=utc(2026, 2, 1, 3, 0),
            settlement_point="HB_WEST",
            settlement_point_type=SettlementPointType.TRADING_HUB,
            lmp=-100.0,
        )
        assert r.lmp == -100.0

    def test_lmp_above_cap_rejected(self):
        with pytest.raises(Exception):
            RTPrices(
                timestamp_utc=utc(2026, 1, 15, 12, 0),
                settlement_point="HB_HUBAVG",
                settlement_point_type=SettlementPointType.TRADING_HUB,
                lmp=5001.0,
            )

    def test_non_utc_timestamp_rejected(self):
        from datetime import timezone as tz
        import pytz
        cst = pytz.timezone("US/Central")
        ts = cst.localize(datetime(2026, 1, 15, 6, 0))
        with pytest.raises(Exception):
            RTPrices(
                timestamp_utc=ts,
                settlement_point="HB_HUBAVG",
                settlement_point_type=SettlementPointType.TRADING_HUB,
                lmp=45.0,
            )

    def test_non_five_min_aligned_rejected(self):
        with pytest.raises(Exception):
            RTPrices(
                timestamp_utc=utc(2026, 1, 15, 12, 3),  # :03 not aligned
                settlement_point="HB_HUBAVG",
                settlement_point_type=SettlementPointType.TRADING_HUB,
                lmp=45.0,
            )


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
                dam_mcpc_regup=1.0,
                dam_mcpc_regdn=0.5,
                dam_mcpc_rrs=0.2,
                dam_mcpc_ecrs=0.1,
                dam_mcpc_nspin=0.8,
            )

    def test_valid(self):
        r = DAMPrices(
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            settlement_point="HB_HUBAVG",
            dam_spp=48.0,
            dam_mcpc_regup=1.5,
            dam_mcpc_regdn=0.7,
            dam_mcpc_rrs=0.3,
            dam_mcpc_ecrs=0.2,
            dam_mcpc_nspin=1.0,
        )
        assert r.dam_spp == 48.0


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
                net_load_mw=99999.0,  # wrong
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
            timestamp_utc=utc(2026, 1, 15, 12, 0),
            as_product=ASProduct.REGUP,
            segments=[
                ASDCSegment(quantity_mw=1000.0, price_per_mw=5.0),
                ASDCSegment(quantity_mw=2000.0, price_per_mw=2.0),
            ],
        )
        assert len(a.segments) == 2

    def test_empty_segments_rejected(self):
        with pytest.raises(Exception):
            ASDCParameters(
                timestamp_utc=utc(2026, 1, 15, 12, 0),
                as_product=ASProduct.ECRS,
                segments=[],
            )
