"""RTC+B market structure constants and helpers."""

from __future__ import annotations

from datetime import UTC, datetime

# RTC+B went live at 00:00 CST on December 5, 2025 = 06:00 UTC
RTCB_LAUNCH_UTC: datetime = datetime(2025, 12, 5, 6, 0, 0, tzinfo=UTC)

# ERCOT price bounds
OFFER_CAP_DOLLARS_PER_MWH = 5_000.0
LOW_PRICE_FLOOR_DOLLARS_PER_MWH = -251.0

# SCED runs approximately every 5 minutes
SCED_INTERVAL_MINUTES = 5

# MIP optimality gap tightening on Jan 8, 2026
MIP_TIGHTEN_UTC: datetime = datetime(2026, 1, 8, 6, 0, 0, tzinfo=UTC)

# v0.1 dataset window
V01_START_UTC: datetime = RTCB_LAUNCH_UTC
V01_END_UTC: datetime = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)  # exclusive

# v1.0 dataset window (target)
V10_START_UTC: datetime = RTCB_LAUNCH_UTC
V10_END_UTC: datetime = datetime(2026, 6, 6, 0, 0, 0, tzinfo=UTC)  # exclusive

# Canonical settlement points for v0.1
# Hubs + major BESS-heavy load zones. This list covers the primary nodes where
# most registered BESS assets in ERCOT cleared as of early 2026.
V01_SETTLEMENT_POINTS: list[str] = [
    # Trading hubs
    "HB_HUBAVG",
    "HB_NORTH",
    "HB_SOUTH",
    "HB_WEST",
    "HB_HOUSTON",
    "HB_PAN",
    # Load zones (BESS-heavy)
    "LZ_NORTH",
    "LZ_SOUTH",
    "LZ_WEST",
    "LZ_HOUSTON",
    "LZ_LCRA",
    "LZ_RAYBN",
    "LZ_AEN",
    "LZ_CPS",
]

# Action space dimension for a BESS participating in RTC+B
# [energy_mw, regup_mw, regdn_mw, rrs_mw, ecrs_mw, nspin_mw]
ACTION_DIM = 6


def is_post_rtcb(ts_utc: datetime) -> bool:
    """Return True if the timestamp is at or after the RTC+B launch."""
    return ts_utc >= RTCB_LAUNCH_UTC


def is_post_mip_tighten(ts_utc: datetime) -> bool:
    """Return True if the timestamp is after the Jan 8, 2026 MIP gap tightening."""
    return ts_utc >= MIP_TIGHTEN_UTC
