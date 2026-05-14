"""Pydantic v2 canonical schemas for post-RTC+B ERCOT market data.

Design notes:
- All timestamps are UTC (ERCOT publishes in CPT/CST; convert on ingest).
- v0.1 covers Dec 5 2025 – Mar 31 2026 (post-RTC+B only).
- AS product enum reflects the five products available post-RTC+B.
  NOTE: The RRS sub-product split (PFR/FFR/UFR) mentioned in ERCOT planning
  documents does not yet appear in the SCED MCPC data product as of Mar 2026;
  RRS is reported as a single product. This will be revisited for v1.0.
- Non-Spin online vs offline distinction: the SCED MCPC product reports a
  single NSPIN category. Separate online/offline clearing is a DAM-level
  distinction; the RT tables reflect aggregate NSPIN MCPC.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────────────────────────


class ASProduct(str, Enum):
    """Ancillary service products as reported in ERCOT SCED MCPC post-RTC+B.

    RRS is currently a single product in MCPC data (no PFR/FFR/UFR split
    visible in the raw SCED data through Mar 2026). This enum will be
    extended if/when ERCOT publishes sub-product level MCPC data.
    """

    REGUP = "REGUP"
    REGDN = "REGDN"
    RRS = "RRS"
    ECRS = "ECRS"
    NSPIN = "NSPIN"


class SettlementPointType(str, Enum):
    TRADING_HUB = "Trading Hub"
    LOAD_ZONE = "Load Zone"
    RESOURCE_NODE = "Resource Node"


# ── Bounds (ERCOT system limits) ──────────────────────────────────────────────

LMP_MIN = -251.0  # ERCOT low-price floor (approximately)
LMP_MAX = 5_000.0  # ERCOT system-wide offer cap
MCPC_MIN = 0.0
MW_MIN = 0.0
SOC_MIN = 0.0
SOC_MAX = 1.0


# ── Type aliases ──────────────────────────────────────────────────────────────

NonNegFloat = Annotated[float, Field(ge=MW_MIN)]
LMPFloat = Annotated[float, Field(ge=LMP_MIN, le=LMP_MAX)]
MCPCFloat = Annotated[float, Field(ge=MCPC_MIN)]
SoCFloat = Annotated[float, Field(ge=SOC_MIN, le=SOC_MAX)]


# ── Canonical tables ──────────────────────────────────────────────────────────


class RTPrices(BaseModel):
    """5-minute RT price record for a single settlement point.

    Source: ERCOT SCED LMP (NP6-788-CD), via gridstatus ErcotAPI.
    Granularity: 5-minute intervals aligned to UTC :00/:05/:10/...
    """

    timestamp_utc: datetime
    settlement_point: str
    settlement_point_type: SettlementPointType
    lmp: LMPFloat
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
            raise ValueError(f"timestamp_utc must be UTC, got {v.tzinfo}")
        return v

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_five_min_aligned(cls, v: datetime) -> datetime:
        if v.second != 0 or v.microsecond != 0 or v.minute % 5 != 0:
            raise ValueError(f"timestamp must be 5-min aligned, got {v}")
        return v


class ASClearing(BaseModel):
    """5-minute RT ancillary service clearing record.

    Source: ERCOT SCED MCPC (security-constrained economic dispatch),
    loaded from pre-downloaded daily Parquet files in data/raw/sced_mcpc/.
    Granularity: approximately every 5 minutes (SCED runs ~every 5 min).
    """

    timestamp_utc: datetime
    as_product: ASProduct
    mcpc: MCPCFloat  # Marginal Clearing Price of Capacity, $/MW
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
            raise ValueError(f"timestamp_utc must be UTC, got {v.tzinfo}")
        return v


class DAMPrices(BaseModel):
    """Hourly DAM price record (energy SPP + all AS MCPCs).

    Source: ERCOT DAM SPP (gridstatus Ercot.get_dam_spp) and
    DAM AS prices (ErcotAPI.get_as_prices).
    Granularity: hourly, aligned to UTC hour boundaries.
    """

    timestamp_utc: datetime
    settlement_point: str
    dam_spp: float  # DAM Settlement Point Price, $/MWh (can be negative)
    dam_mcpc_regup: MCPCFloat
    dam_mcpc_regdn: MCPCFloat
    dam_mcpc_rrs: MCPCFloat
    dam_mcpc_ecrs: MCPCFloat
    dam_mcpc_nspin: MCPCFloat
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc_and_hourly(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
            raise ValueError(f"timestamp_utc must be UTC, got {v.tzinfo}")
        if v.minute != 0 or v.second != 0 or v.microsecond != 0:
            raise ValueError(f"DAM timestamp must be hour-aligned, got {v}")
        return v


class SystemConditions(BaseModel):
    """5-minute system-level load, wind, and solar observation.

    Sources:
      - load_actual: Ercot.get_hourly_load_post_settlements (upsampled 5-min)
      - wind/solar actual: ErcotAPI.get_wind_actual_and_forecast_hourly
      - wind/solar forecast: same endpoint (STWPF/STPPF products)
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
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
            raise ValueError(f"timestamp_utc must be UTC, got {v.tzinfo}")
        return v

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
    """Single (quantity, price) point on an ancillary service demand curve."""

    quantity_mw: NonNegFloat
    price_per_mw: MCPCFloat


class ASDCParameters(BaseModel):
    """ASDC (Ancillary Service Demand Curve) parameters for one product interval.

    ERCOT publishes ASDCs that define how much AS capacity ERCOT is willing
    to procure at each price tier. These are used in both DAM and (post-RTC+B)
    in real-time SCED co-optimization.

    Note: ASDC publication granularity and access method require verification
    against the actual ERCOT API. This schema assumes hourly granularity;
    update if the actual data is at a different resolution.
    """

    timestamp_utc: datetime
    as_product: ASProduct
    segments: list[ASDCSegment]
    is_post_rtcb: bool = True

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v).total_seconds() != 0:
            raise ValueError(f"timestamp_utc must be UTC, got {v.tzinfo}")
        return v

    @field_validator("segments")
    @classmethod
    def segments_nonempty(cls, v: list[ASDCSegment]) -> list[ASDCSegment]:
        if not v:
            raise ValueError("ASDC must have at least one segment")
        return v


class BESSMetadata(BaseModel):
    """Static metadata for a registered Battery Energy Storage System.

    This table defines the physical parameters of BESS assets used in
    simulation and evaluation. Populated from ERCOT resource registry data.
    """

    resource_name: str
    settlement_point: str
    power_mw: NonNegFloat  # nameplate AC power capacity
    energy_mwh: NonNegFloat  # usable energy capacity
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
