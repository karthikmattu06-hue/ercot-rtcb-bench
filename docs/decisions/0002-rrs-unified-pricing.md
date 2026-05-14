# ADR 0002 — RRS Is a Single Priced Product; Sub-Products PFR / FFR / UFR Are Award-Only

**Status:** Accepted (2026-05-14)

**Context.** ERCOT's Responsive Reserve Service (RRS) under RTC+B contains
three sub-products: RRS-PFR (Primary Frequency Response), RRS-FFR (Fast
Frequency Response), and RRS-UFR (Under-Frequency Relay, load-side).
Schema designers initially assumed three separate MCPCs. Empirical
inspection of ERCOT's "Real-Time Clearing Prices for Capacity by SCED
Interval" through March 2026 shows only a single aggregated RRS MCPC,
alongside Reg-Up, Reg-Down, ECRS, and Non-Spin. Primary sources (Nodal
Protocol Section 4.4.12 as modified by NPRR 1268; NPRR 828 introducing
FFR as a subset of RRS; the ERCOT "RTC+B Telemetry Changes" deck dated
6/14/2024) confirm that RRS sub-products share a single Ancillary
Service Demand Curve and a single shadow price in the SCED MIQP.
Sub-products are differentiated at qualification, telemetry capability,
AS Trade hierarchy, and per-sub-product *award* level — not at clearing.
Per Grid Status's Feb 2026 post-cutover analysis, BESS resources
overwhelmingly take their RRS awards as RRS-FFR; RRS-UFR is a load-side
product not relevant to BESS.

**Decision.** The benchmark will model **one RRS price and three RRS
award columns**.

- `prices_rt.mcpc_rrs : float` only (no `_pfr`, `_ffr`, `_ufr` price columns).
- `awards.award_rrs_pfr`, `awards.award_rrs_ffr`, `awards.award_rrs_ufr : float`,
  with invariant `mcpc_rrs × (award_pfr + award_ffr + award_ufr) =
  rrs_capacity_payment`.
- The bidder action space exposes one continuous `a_rrs ∈ [0, P_rated]`.
  An optional resource-capability vector `(q_pfr, q_ffr, q_ufr) ∈ {0,1}³`
  partitions awards internally; for BESS, `q_ufr = 0` by default.
- The MILP discretizes one RRS ASDC (the shared AORDC scaled by the RRS
  AS Plan target from `np4-33-CD`).

**Consequences.**
- `RTPrices` holds five MCPC columns total, matching ERCOT's MIS exactly;
  no null PFR/FFR/UFR price columns.
- `Awards` preserves sub-product columns so settlement and per-sub-product
  duration enforcement can be modeled if a future ADR refines the SOC check.
- Effective action dimensionality for BESS is 5 (energy + Reg-Up +
  Reg-Down + RRS + ECRS + Non-Spin = 6, minus implicit RRS-UFR).
  Documented in the bidder API.
- The MILP is smaller and faster (one RRS segment family).
- Robust to a future ERCOT decision to split RRS pricing: adding
  sub-product price columns is non-breaking.

**Alternatives considered.**
1. Three separate RRS MCPC columns with identical values — rejected;
   implies a distinction ERCOT does not make.
2. Single price, single award column — rejected; loses information
   needed for sub-product duration enforcement and 60-day data reconciliation.
3. Drop RRS from the bidder action space — rejected; RRS is real money
   for BESS (Modo Dec 2025: RRS-FFR sustains storage's award dominance).

**References.**
ERCOT *RTC+B Telemetry Changes* (6/14/2024); *Load Resource Overview and
Changes Introduced With RTC+B* (7/9/2025, ICCP V1.4); NPRR 828 *Include
Fast Frequency Response as a Subset of Responsive Reserve*; NPRR 1268
*RTC – Modification of Ancillary Service Demand Curves* (1/28/2025);
Nodal Protocol §4.4.12, §6.5.7.6.2.2; ERCOT MIS *Real-Time Market*
product catalog (ercot.com/mktinfo/rtm); Grid Status *RTC+B, 60 Days
Later in ERCOT* (Feb 2026); Potomac Economics (IMM) *2024 State of the
Market Report* (June 2025), Recommendation 2024-1a.
