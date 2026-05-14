"""BESS physical model parameters (Task 4 — MILP baseline)."""

from __future__ import annotations

from dataclasses import dataclass

from ercot_rtcb_bench.data.schema import BESSMetadata

DT_HOURS = 5 / 60  # 5-minute SCED interval in hours


@dataclass
class BESSParams:
    """Physical parameters for one BESS resource used in the MILP formulation.

    All power quantities in MW; energy in MWh; SoC is fractional [0, 1].
    """

    resource_name: str
    power_mw: float
    energy_mwh: float
    rte: float
    soc_min: float = 0.0
    soc_max: float = 1.0
    soc_init: float = 0.5
    dt_hours: float = DT_HOURS
    nspin_soc_hours: float = 4.0  # SOC duration req for Non-Spin (ADR 0004 / NPRR 1096)

    @property
    def soc_energy_min(self) -> float:
        return self.soc_min * self.energy_mwh

    @property
    def soc_energy_max(self) -> float:
        return self.soc_max * self.energy_mwh

    @property
    def soc_energy_init(self) -> float:
        return self.soc_init * self.energy_mwh

    @classmethod
    def from_metadata(
        cls,
        meta: BESSMetadata,
        soc_init: float = 0.5,
        soc_min: float = 0.0,
        soc_max: float = 1.0,
    ) -> "BESSParams":
        return cls(
            resource_name=meta.resource_name,
            power_mw=meta.power_mw,
            energy_mwh=meta.energy_mwh,
            rte=meta.round_trip_efficiency,
            soc_init=soc_init,
            soc_min=soc_min,
            soc_max=soc_max,
        )

    @classmethod
    def default_100mw_4hr(cls, resource_name: str = "BATT_BENCH") -> "BESSParams":
        """100 MW / 400 MWh, 88% RTE — a representative ERCOT BESS."""
        return cls(
            resource_name=resource_name,
            power_mw=100.0,
            energy_mwh=400.0,
            rte=0.88,
        )
