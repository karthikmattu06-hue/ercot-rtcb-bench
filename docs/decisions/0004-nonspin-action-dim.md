# ADR 0004 — Non-Spin: Single Action Dimension in Real-Time, Two Product Codes in Day-Ahead

**Status:** Accepted (2026-05-14)

**Context.** Pre-RTC+B and under RTC+B, the ERCOT Day-Ahead Market
publishes Non-Spin Online and Non-Spin Offline as two separate MCPC
products (NP4-188-CD). Real-Time post-RTC+B publishes a single Non-Spin
MCPC (Real-Time Clearing Prices for Capacity by SCED Interval lists
exactly: Reg-Up, Reg-Down, RRS, Non-Spin, ECRS). PCI Energy Solutions
confirms RTC+B retired the `OFFNS` COP status. The asymmetry is
intentional: in DAM, on/off matters for thermal Quick-Start units
booking commitment costs; in RT, SCED has telemetered resource-state
visibility and the on/off attribute is a deployment-mechanism difference
(UDSP-SCED for online Non-Spin vs ASM XML for offline Non-Spin per
RTC+B ICCP V1.4) rather than a priced product. For BESS, ERCOT models
the ESR as a single unified resource (NPRR 1014); ESR Non-Spin capacity
occupies its own row in the System Ancillary Service Capacity Monitor.
The 4-hour SOC duration requirement (which Engie and Jupiter publicly
dissented on) applies uniformly to BESS Non-Spin awards under RTC+B;
it does not distinguish online from offline.

**Decision.** Use **one Non-Spin action dimension in RT** and **two
Non-Spin product codes in DAM**, joined by a shared `product_family` key.

- `prices_rt.mcpc_nspin : float` — single RT MCPC.
- `prices_dam.mcpc_nspin_online`, `prices_dam.mcpc_nspin_offline : float`
  — two DAM MCPC columns, preserved as published.
- `product_family` registry maps both DAM codes to family `nspin`.
- Bidder RT action: single `a_nspin ∈ [0, P_rated]`. Bidder DAM: only
  `a_nspin_online` exposed for BESS by default; `a_nspin_offline` is
  opt-in via `config.bidder.dam_offline_nspin = false` (default).
- DAM→RT imbalance: `dam.award_nspin_online + dam.award_nspin_offline →
  dam_position_nspin`, netted against `rt.award_nspin`.
- MILP includes forward-looking SOC constraint: `SOC_t ≥ 4 ×
  award_nspin_t` for every interval `t` Non-Spin is held.

**Consequences.**
- The schema honors ERCOT's actual published structure on both sides
  without phantom RT product codes.
- The 6-D action-space framing for BESS remains accurate (consistent
  with ADR 0002's RRS collapse).
- DAM split is exposed for thermal benchmarks; BESS users ignore it.
- If a future NPRR re-introduces a split RT Non-Spin MCPC (none in flight
  as of Feb 2026), the schema change is additive.
- The 4-hour SOC constraint is conservative for BESS revenue; users may
  disable it at config level with a documented warning that SCED
  pre-processing mitigates non-compliant offers in production.

**Alternatives considered.**
1. Two Non-Spin product codes in RT mirroring DAM — rejected; ERCOT
   does not publish two RT MCPCs.
2. One Non-Spin product code in DAM — rejected; loses information
   present in NP4-188-CD and breaks imbalance computation for thermal
   resources.
3. No 4-hour SOC constraint — rejected; without it, the MILP overstates
   BESS Non-Spin revenue.
4. Per-sub-state SOC differentiation (online 30-min, offline 4-hr) —
   rejected; current ERCOT documentation applies 4-hr uniformly under RTC+B.

**References.**
ERCOT *Real-Time Market* product catalog (ercot.com/mktinfo/rtm); ERCOT
DAM product NP4-188-CD; ERCOT *RTC+B Telemetry Changes* (6/14/2024);
*Load Resource Overview and Changes Introduced With RTC+B* (7/9/2025,
ICCP V1.4); PCI Energy Solutions *ERCOT RTCB Go-Live: Key Market Changes
Starting Dec. 5, 2025* (12/3/2025); NPRR 1008 (RTC), NPRR 1014
(Single-Model ESR), NPRR 1186 (Pre-RTC+B ESR SOC monitoring), NPRR 1096
(4-hour Non-Spin duration); ERCOT System Ancillary Service Capacity
Monitor (ercot.com/gridmktinfo/dashboards/ancillaryservicecapacitymonitor);
Modo Energy *RTC+B: How Real-Time Co-Optimization will affect Ancillary
Services for batteries in ERCOT*; Modo Energy *ME BESS ERCOT December
2025: The First Month of RTC+B*; Tyba *Added complexity with ERCOT RTC+B
Duration Requirements*; Yes Energy *ERCOT RTC+B Market Redesign FAQ Part II*;
ERCOT TAC summary, January 2026 (no online/offline-split NPRR in flight).
