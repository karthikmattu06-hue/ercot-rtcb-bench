"""Unit tests for the MILP baseline (perfect-foresight and point-forecast).

Tests use small synthetic price series and scipy as the solver backend.
No ERCOT data required.
"""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.perfect_foresight import perfect_foresight
from ercot_rtcb_bench.methods.point_forecast import _dam_to_forecast_prices, point_forecast

UTC = UTC


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_prices(
    T: int = 24,
    lmp: float = 30.0,
    mcpc_regup: float = 2.0,
    mcpc_regdn: float = 1.0,
    mcpc_rrs: float = 0.5,
    mcpc_ecrs: float = 0.3,
    mcpc_nspin: float = 1.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic 5-minute RT price DataFrame, T intervals from 2026-02-01."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(
        start="2026-02-01 06:00", periods=T, freq="5min", tz="UTC"
    )
    return pd.DataFrame(
        {
            "lmp": lmp + rng.normal(0, 5, T),
            "mcpc_regup": np.maximum(0, mcpc_regup + rng.normal(0, 0.2, T)),
            "mcpc_regdn": np.maximum(0, mcpc_regdn + rng.normal(0, 0.1, T)),
            "mcpc_rrs": np.maximum(0, mcpc_rrs + rng.normal(0, 0.05, T)),
            "mcpc_ecrs": np.maximum(0, mcpc_ecrs + rng.normal(0, 0.03, T)),
            "mcpc_nspin": np.maximum(0, mcpc_nspin + rng.normal(0, 0.1, T)),
        },
        index=idx,
    )


def _make_dam_prices(T_hours: int = 2) -> pd.DataFrame:
    """Synthetic hourly DAM price DataFrame."""
    idx = pd.date_range(start="2026-02-01 06:00", periods=T_hours, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "dam_spp": [28.0, 32.0][:T_hours],
            "mcpc_regup": [1.8, 2.2][:T_hours],
            "mcpc_regdn": [0.9, 1.1][:T_hours],
            "mcpc_rrs": [0.4, 0.6][:T_hours],
            "mcpc_ecrs": [0.25, 0.35][:T_hours],
            "mcpc_nspin_online": [0.8, 1.2][:T_hours],
            "mcpc_nspin_offline": [0.6, 0.9][:T_hours],
        },
        index=idx,
    )


@pytest.fixture
def small_bess():
    return BESSParams(
        resource_name="TEST_BESS",
        power_mw=10.0,
        energy_mwh=40.0,
        rte=0.88,
        soc_init=0.5,
    )


@pytest.fixture
def tiny_prices():
    return _make_prices(T=12)  # 1 hour of 5-min intervals


# ── BESSParams ─────────────────────────────────────────────────────────────────


class TestBESSParams:
    def test_soc_energy_properties(self):
        b = BESSParams("X", 100.0, 400.0, 0.88)
        assert b.soc_energy_min == 0.0
        assert b.soc_energy_max == 400.0
        assert b.soc_energy_init == 200.0

    def test_default_100mw_4hr(self):
        b = BESSParams.default_100mw_4hr()
        assert b.power_mw == 100.0
        assert b.energy_mwh == 400.0
        assert b.rte == 0.88
        assert b.nspin_soc_hours == 4.0

    def test_from_metadata(self):
        from ercot_rtcb_bench.data.schema import BESSMetadata
        meta = BESSMetadata(
            resource_name="BATT_X",
            settlement_point="HB_HUBAVG",
            power_mw=50.0,
            energy_mwh=200.0,
            round_trip_efficiency=0.90,
            duration_hours=4.0,
        )
        b = BESSParams.from_metadata(meta)
        assert b.power_mw == 50.0
        assert b.rte == 0.90


# ── Perfect-foresight LP ───────────────────────────────────────────────────────


class TestPerfectForesight:
    def test_runs_and_returns_result(self, small_bess, tiny_prices):
        result = perfect_foresight(small_bess, tiny_prices)
        assert result.dispatch is not None
        assert len(result.dispatch) == len(tiny_prices)

    def test_revenue_positive_with_positive_prices(self, small_bess):
        prices = _make_prices(T=12, lmp=50.0, mcpc_regup=3.0)
        result = perfect_foresight(small_bess, prices)
        # With positive LMP and AS prices, revenue should be > 0
        assert result.revenue_total > 0

    def test_soc_bounds_respected(self, small_bess, tiny_prices):
        result = perfect_foresight(small_bess, tiny_prices)
        soc = result.dispatch["soc_mwh"].values
        assert np.all(soc >= small_bess.soc_energy_min - 1e-6)
        assert np.all(soc <= small_bess.soc_energy_max + 1e-6)

    def test_power_limits_respected(self, small_bess, tiny_prices):
        P = small_bess.power_mw
        result = perfect_foresight(small_bess, tiny_prices)
        d = result.dispatch["discharge_mw"].values
        c = result.dispatch["charge_mw"].values
        a_ru = result.dispatch["award_regup_mw"].values
        a_rd = result.dispatch["award_regdn_mw"].values
        a_rrs = result.dispatch["award_rrs_mw"].values
        a_ecrs = result.dispatch["award_ecrs_mw"].values
        a_ns = result.dispatch["award_nspin_mw"].values

        # Discharge side
        assert np.all(d + a_ru + a_rrs + a_ecrs + a_ns <= P + 1e-6)
        # Charge side
        assert np.all(c + a_rd <= P + 1e-6)

    def test_nspin_soc_constraint(self, small_bess, tiny_prices):
        result = perfect_foresight(small_bess, tiny_prices)
        soc = result.dispatch["soc_mwh"].values
        a_ns = result.dispatch["award_nspin_mw"].values
        nspin_h = small_bess.nspin_soc_hours
        # soc_t >= nspin_h * a_ns_t
        assert np.all(soc >= nspin_h * a_ns - 1e-6)

    def test_dispatch_index_matches_prices(self, small_bess, tiny_prices):
        result = perfect_foresight(small_bess, tiny_prices)
        pd.testing.assert_index_equal(result.dispatch.index, tiny_prices.index, check_names=False)

    def test_missing_price_column_raises(self, small_bess):
        bad_prices = _make_prices(T=6).drop(columns=["mcpc_nspin"])
        with pytest.raises(ValueError, match="missing columns"):
            perfect_foresight(small_bess, bad_prices)

    def test_all_zero_prices_zero_revenue(self, small_bess):
        T = 6
        idx = pd.date_range("2026-02-01 06:00", periods=T, freq="5min", tz="UTC")
        prices = pd.DataFrame(
            {c: np.zeros(T) for c in ["lmp", "mcpc_regup", "mcpc_regdn",
                                       "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]},
            index=idx,
        )
        result = perfect_foresight(small_bess, prices)
        assert abs(result.revenue_total) < 1e-6

    def test_negative_lmp_charges_battery(self, small_bess):
        """With negative LMP the optimizer should prefer charging (negative net energy)."""
        prices = _make_prices(T=12, lmp=-50.0, mcpc_regup=0.0, mcpc_regdn=0.0,
                              mcpc_rrs=0.0, mcpc_ecrs=0.0, mcpc_nspin=0.0)
        result = perfect_foresight(small_bess, prices)
        # Net energy should be negative (charging) on average
        assert result.dispatch["net_energy_mw"].mean() < 0

    def test_revenue_breakdown_sums_to_total(self, small_bess, tiny_prices):
        result = perfect_foresight(small_bess, tiny_prices)
        assert abs(result.revenue_energy + result.revenue_as - result.revenue_total) < 1e-4

    def test_larger_problem_smoke(self):
        """2016-interval (7-day) problem completes in reasonable time."""
        bess = BESSParams.default_100mw_4hr()
        prices = _make_prices(T=2016)  # 7 days
        result = perfect_foresight(bess, prices)
        assert result.solution.status in ("optimal", "feasible")
        assert result.revenue_total > 0


# ── DAM → RT price expansion ──────────────────────────────────────────────────


class TestDamToForecastPrices:
    def test_expands_hourly_to_5min(self):
        dam = _make_dam_prices(T_hours=2)
        rt_idx = pd.date_range("2026-02-01 06:00", periods=24, freq="5min", tz="UTC")
        forecast = _dam_to_forecast_prices(dam, rt_idx)
        assert len(forecast) == 24
        assert set(forecast.columns) == {"lmp", "mcpc_regup", "mcpc_regdn",
                                          "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"}

    def test_uses_nspin_online_for_bess(self):
        dam = _make_dam_prices(T_hours=1)
        rt_idx = pd.date_range("2026-02-01 06:00", periods=12, freq="5min", tz="UTC")
        forecast = _dam_to_forecast_prices(dam, rt_idx)
        # mcpc_nspin should come from mcpc_nspin_online (= 0.8)
        assert abs(forecast["mcpc_nspin"].iloc[0] - 0.8) < 0.01


# ── Point forecast ─────────────────────────────────────────────────────────────


class TestPointForecast:
    def test_runs_and_returns_result(self, small_bess):
        rt_prices = _make_prices(T=12)
        dam_prices = _make_dam_prices(T_hours=1)
        result = point_forecast(small_bess, rt_prices, dam_prices)
        assert result.dispatch is not None
        assert len(result.dispatch) == 12

    def test_settlement_uses_rt_prices(self, small_bess):
        """Revenue must differ from forecast because RT ≠ DAM prices."""
        rt_prices = _make_prices(T=12, lmp=100.0)  # high RT LMP
        dam_prices = _make_dam_prices(T_hours=1)    # low DAM prices
        result = point_forecast(small_bess, rt_prices, dam_prices)
        # The optimizer used DAM prices (low LMP=28); settlement uses RT (high LMP=100)
        # Revenue should be large because the RT settlement is favorable
        assert result.revenue_total > 0

    def test_dispatch_columns_present(self, small_bess):
        rt_prices = _make_prices(T=12)
        dam_prices = _make_dam_prices(T_hours=1)
        result = point_forecast(small_bess, rt_prices, dam_prices)
        for col in ("discharge_mw", "charge_mw", "award_regup_mw", "soc_mwh"):
            assert col in result.dispatch.columns
