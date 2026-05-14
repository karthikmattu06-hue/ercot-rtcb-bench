"""Pydantic v2 canonical schemas for post-RTC+B ERCOT market data.

Schema decisions:
- ADR 0002: RRS is one priced product (mcpc_rrs only); Awards preserves
  PFR/FFR/UFR sub-product columns for settlement reconciliation.
- ADR 0003: ASDCParameters sourced from AORDC xlsx; ASDCHourly from np4-212-cd.
- ADR 0004: Non-Spin has one RT MCPC (mcpc_nspin); DAM exposes two codes
  (mcpc_nspin_online, mcpc_nspin_offline); joined by PRODUCT_FAMILY registry.
- All timestamps are UTC. ERCOT publishes in CPT; convert on ingest.
- v0.1 covers Dec 5 2025 – Mar 31 2026 (post-RTC+B only).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────


class ASProduct(str, Enum):
    """The five AS products reported in ERCOT SCED MCPC post-RTC+B.

    Exactly five values — this is a regression test anchor (ADR 0002).
    RRS sub-products (PFR/FFR/UFR) share one MCPC and one enum value.
    """

    REGUP = "regup"
    REGDN = "regdn"
    RRS = "rrs"
    ECRS = "ecrs"
    NSPIN = "nspin"


class SettlementPointType(str, Enum):
    TRADING_HUB = "Trading Hub"
    LOAD_ZONE = "Load Zone"
    RESOURCE_NODE = "Resource Node"


# ── Product family registry (ADR 0004) ───────────────────────────────────────

PRODUCT_FAMILY: dict[str, str] = {
    "regup": "regup",
    "regdn": "regdn",
    "rrs": "rrs",
    "ecrs": "ecrs",
    "nspin": "nspin",
    "nspin_online": "nspin",   # DAM-only code → RT family
    "nspin_offline": "nspin",  # DAM-only code → RT family
}


# ── ERCOT system-wide price bounds ────────────────────────────────────────────

LMP_MIN = -251.0
LMP_MAX = 5_000.0
MCPC_MIN = 0.0
MW_MIN = 0.0
SOC_MIN = 0.0
SOC_MAX = 1.0


# ── Annotated type aliases ────────────────────────────────────────────────────

NonNegFloat = Annotated[float, Field(ge=MW_MIN)]
LMPFloat = Annotated[float, Field(ge=LMP_MIN, le=LMP_MAX)]
MCPCFloat = Annotated[float, Field(ge=MCPC_MIN)]
SoCFloat = Annotated[float, Field(ge=SOC_MIN, le=SOC_MAX)]


# ── Timestamp validators (reusable) ──────────────────────────────────────────

def _validate_utc(v: datetime) -> datetime:
    if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
        raise ValueError(f"timestamp must be UTC, got tzinfo={v.tzinfo}")
    return v


def _validate_five_min(v: datetime) -> datetime:
    if v.second != 0 or v.microsecond != 0 or v.minute % 5 != 0:
        raise ValueError(f"timestamp must be 5-min aligned (:00/:05/...), got {v}")
    return v


def _validate_hourly(v: datetime) -> datetime:
    if v.minute != 0 or v.second != 0 or v.microsecond != 0:
        raise ValueError(f"timestamp must be hour-aligned, got {v}")
    return v


# ── Canonical tables ──────────────────────────────────────────────────────────


class RTPrices(BaseModel):
    """5-minute RT energy and AS clearing prices for one settlement point.

    Five MCPC columns match ERCOT's SCED interval clearing price publication
    exactly. No sub-product MCPC columns are present (ADR 0002: RRS unified;
    ADR 0004: NSPIN is a single RT product).

    Source: SCED LMP (NP6-788-CD) for energy; SCED MCPC for AS prices.
    """

    timestamp_utc: datetime
    settlement_point: str
    settlement_point_type: SettlementPointType
    lmp: LMPFloat
    mcpc_regup: MCPCFloat
    mcpc_regdn: MCPCFloat
    mcpc_rrs: MCPCFloat    # single RRS price; sub-product awards in Awards table (ADR 0002)
    mcpc_ecrs: MCPCFloat
    mcpc_nspin: MCPCFloat  # single RT Non-Spin price (ADR 0004)
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def utc(cls, v: datetime) -> datetime:
        return _validate_utc(v)

    @field_validator("timestamp_utc")
    @classmethod
    def five_min(cls, v: datetime) -> datetime:
        return _validate_five_min(v)


class DAMPrices(BaseModel):
    """Hourly DAM energy SPP and AS MCPC.

    Non-Spin is preserved as two DAM product codes (ADR 0004): online and
    offline, matching NP4-188-CD. Both map to RT family 'nspin' via PRODUCT_FAMILY.

    Source: DAM SPP (Ercot.get_dam_spp); DAM AS prices (ErcotAPI.get_as_prices).
    """

    timestamp_utc: datetime
    settlement_point: str
    dam_spp: float  # DAM SPP can be negative
    mcpc_regup: MCPCFloat
    mcpc_regdn: MCPCFloat
    mcpc_rrs: MCPCFloat
    mcpc_ecrs: MCPCFloat
    mcpc_nspin_online: MCPCFloat   # DAM Non-Spin Online (ADR 0004)
    mcpc_nspin_offline: MCPCFloat  # DAM Non-Spin Offline (ADR 0004)
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def utc_hourly(cls, v: datetime) -> datetime:
        _validate_utc(v)
        return _validate_hourly(v)


class ASClearing(BaseModel):
    """5-minute SCED AS clearing price record (long format, one row per product).

    Deprecated: superseded by the MCPC columns on RTPrices (wide format) for
    the canonical v0.1 tables. ASClearing is retained for the raw sced_mcpc
    representation; downstream consumers should prefer RTPrices.

    Source: SCED MCPC raw daily Parquet files.
    """

    timestamp_utc: datetime
    as_product: ASProduct
    mcpc: MCPCFloat
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def utc(cls, v: datetime) -> datetime:
        return _validate_utc(v)


class Awards(BaseModel):
    """Per-resource per-interval AS awards (ADR 0002).

    RRS sub-product awards (PFR/FFR/UFR) are preserved here for settlement
    reconciliation, even though they share one clearing price (mcpc_rrs on
    RTPrices). Invariant: mcpc_rrs × (award_rrs_pfr + award_rrs_ffr +
    award_rrs_ufr) = rrs_capacity_payment for this resource at this interval.

    For BESS resources, award_rrs_ufr == 0 (load-side product).
    Non-Spin uses a single RT award column (ADR 0004).
    """

    timestamp_utc: datetime
    resource_name: str
    award_energy: float       # MW; positive = discharge, negative = charge
    award_regup: NonNegFloat
    award_regdn: NonNegFloat
    award_rrs_pfr: NonNegFloat
    award_rrs_ffr: NonNegFloat
    award_rrs_ufr: NonNegFloat  # zero for BESS
    award_ecrs: NonNegFloat
    award_nspin: NonNegFloat    # single RT Non-Spin award (ADR 0004)
    is_bess: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def utc_five_min(cls, v: datetime) -> datetime:
        _validate_utc(v)
        return _validate_five_min(v)

    @model_validator(mode="after")
    def bess_ufr_zero(self) -> "Awards":
        if self.is_bess and self.award_rrs_ufr != 0.0:
            raise ValueError("BESS resources must have award_rrs_ufr == 0 (load-side product)")
        return self


class ASDCParameters(BaseModel):
    """Static AORDC mixture-normal formula constants (ADR 0003).

    Sourced from ERCOT AORDC Regression Fit Parameters xlsx (9/30/2025).
    Keyed by (as_product, effective_date).
    Validator: mix_weight_30min + mix_weight_60min ≈ 1.0.

    These constants parameterize the ASDC shape; per-hour realized curves
    are in ASDCHourly (sourced from np4-212-cd).
    """

    as_product: ASProduct
    effective_date: date
    mu: float
    sigma: float
    mix_weight_30min: float
    mix_weight_60min: float
    voll: float           # Value of Lost Load, $/MWh
    voll_cap_offset: float  # $250 per NPRR 1268
    min_step_floor: float   # ASDC price floor $/MW-h per NPRR 1268
    source_url: str
    source_doc_revision: str

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ASDCParameters":
        total = self.mix_weight_30min + self.mix_weight_60min
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"mix_weight_30min + mix_weight_60min must equal 1.0, got {total}"
            )
        return self


class ASDCHourly(BaseModel):
    """Per-hour realized ASDC breakpoints from np4-212-cd (ADR 0003).

    Keyed by (operating_date, hour_ending, as_product, segment_index).
    hour_ending is 1..24 in Central Time (ERCOT convention).
    breakpoint_mw should be increasing and breakpoint_price decreasing
    within a (date, hour, product) group.
    """

    operating_date: date
    hour_ending: Annotated[int, Field(ge=1, le=24)]
    as_product: ASProduct
    segment_index: Annotated[int, Field(ge=0)]
    breakpoint_mw: NonNegFloat
    breakpoint_price: float   # $/MW-h; non-negative but not enforced here (VOLL can vary)
    as_plan_mw: NonNegFloat
    source_filename: str


class SystemConditions(BaseModel):
    """5-minute system-level load, wind, solar observation.

    Sources:
      load_actual: Ercot.get_hourly_load_post_settlements (5-min proxy)
      wind/solar actual+forecast: ErcotAPI hourly endpoints
    """

    timestamp_utc: datetime
    total_load_mw: NonNegFloat
    load_forecast_mw: NonNegFloat
    wind_actual_mw: NonNegFloat
    wind_forecast_mw: NonNegFloat
    solar_actual_mw: NonNegFloat
    solar_forecast_mw: NonNegFloat
    net_load_mw: float  # load - wind_actual - solar_actual; can be negative
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def utc(cls, v: datetime) -> datetime:
        return _validate_utc(v)

    @model_validator(mode="after")
    def net_load_consistent(self) -> "SystemConditions":
        expected = self.total_load_mw - self.wind_actual_mw - self.solar_actual_mw
        if abs(self.net_load_mw - expected) > 1.0:
            raise ValueError(
                f"net_load_mw {self.net_load_mw:.1f} != "
                f"load - wind - solar = {expected:.1f}"
            )
        return self


class ASDCSegment(BaseModel):
    """Single (quantity, price) breakpoint on an ASDC (legacy helper)."""

    quantity_mw: NonNegFloat
    price_per_mw: MCPCFloat


class BESSMetadata(BaseModel):
    """Static physical parameters for a registered BESS resource."""

    resource_name: str
    settlement_point: str
    power_mw: NonNegFloat
    energy_mwh: NonNegFloat
    round_trip_efficiency: Annotated[float, Field(gt=0.0, le=1.0)]
    duration_hours: NonNegFloat  # energy_mwh / power_mw

    @model_validator(mode="after")
    def duration_consistent(self) -> "BESSMetadata":
        if self.power_mw > 0:
            expected = self.energy_mwh / self.power_mw
            if abs(self.duration_hours - expected) > 0.01:
                raise ValueError(
                    f"duration_hours {self.duration_hours:.3f} != "
                    f"energy/power = {expected:.3f}"
                )
        return self
