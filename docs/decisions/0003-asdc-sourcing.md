# ADR 0003 — ASDC Parameters Are Sourced from EMIL `np4-212-cd` (Daily) and the AORDC Regression Fit Parameters File (Static)

**Status:** Accepted (2026-05-14)

**Context.** Ancillary Service Demand Curves (ASDCs) are the
price-responsive demand curves SCED uses to set AS shadow prices under
RTC+B. ASDC parameters were not surfaced through gridstatus or other
third-party APIs at v0.1, and the `ASDCParameters` table was left empty.
Primary research has identified that ERCOT publishes ASDCs in two
complementary forms: (1) static formula constants — the AORDC
mixture-normal parameters (μ, σ, weights, VOLL cap) governing the
Reg-Up / RRS / ECRS ASDC family plus separate Non-Spin calibration,
posted as an xlsx on the RTCBTF Key Documents page on 9/30/2025 ("AORDC
Regression Fit Parameters for RTC+B Go-Live"), announced via Market
Notice M-B092325-01; (2) per-hour realized curves via EMIL `np4-212-cd`
"DAM and SCED Ancillary Service Demand Curves" (Active since 12-5-2025,
daily, public, zip/csv/xml, Report Type ID 24893). The 2026 AS
Methodology (TAC-endorsed 8/27/2025, effective 1/1/2026) changes ECRS
and Non-Spin *quantities* via a probabilistic model but not curve shape,
so an effective-date column is required.

**Decision.** Populate `ASDCParameters` from the AORDC xlsx and ingest
`np4-212-cd` daily into `ASDCHourly`.

- `ASDCParameters` rows keyed by `(as_product, effective_date)`. Columns:
  `as_product ∈ {regup, regdn, rrs, ecrs, nspin}`, `mu`, `sigma`,
  `mix_weight_30min`, `mix_weight_60min`, `voll`, `voll_cap_offset`,
  `min_step_floor` (NPRR 1268 floor), `effective_date`, `source_url`,
  `source_doc_revision`.
- `ASDCHourly` rows keyed by `(operating_date, hour_ending, as_product,
  segment_index)`. Columns: `breakpoint_mw`, `breakpoint_price`,
  `as_plan_mw`, `source_filename`.
- MILP discretizes `ASDCHourly` into K=10 SOS2 linear segments per
  product-hour. `ASDCParameters` is a unit-test oracle (curve
  reconstruction must match published breakpoints to ≤$0.10/MW-h).
- Inversion of ASDCs from cleared (MCPC, MW) data is *not* a primary
  source; diagnostic only.

**Consequences.**
- The empty-table blocker on `ASDCParameters` is closed.
- The benchmark can replicate SCED's AS pricing component to within
  published precision.
- Adding a new AS product (e.g., DRRS per NPRR 1235) is an additive row,
  no schema change.
- Daily `np4-212-cd` ingest adds a 31-day rolling pipeline; historical
  backfill requires MIS archive scraping.
- Future IMM-driven reformulation (Recommendation 2024-1a) is handled
  by a new `effective_date` row.
- gridstatus wires Report Type IDs 24893 and 24886 but does not yet
  publish parsed ASDC tables; fetch directly from ERCOT.

**Alternatives considered.**
1. Invert ASDCs from cleared data — rejected; near-zero RT AS prices
   93% of the time (Modo Dec 2025) make fits unstable.
2. Hard-coded step ASDC (Enverus-style) — rejected; violates the
   benchmark's commitment to reproduce ERCOT clearing exactly.
3. Wait for a third-party vendor to redistribute parameters — rejected;
   none does, and the primary product is public, daily, and machine-readable.

**References.**
EMIL `np4-212-cd` *DAM and SCED Ancillary Service Demand Curves*; EMIL
`np4-215-cd` *Weekly RUC Ancillary Service Demand Curves*; ERCOT *AORDC
Regression Fit Parameters for RTC+B Go-Live* xlsx (9/30/2025, RTCBTF Key
Documents); ERCOT Market Notice M-B092325-01; ERCOT *ASDC Generator and
Visualization Tool* xlsm (10/8/2025); NPRR 1268, NPRR 1269, NPRR 1270;
Nodal Protocol §4.4.12 (gray-boxed); ERCOT *2024 Biennial ORDC Report*
(10/31/2024); Potomac Economics *2024 State of the Market Report*,
Recommendation 2024-1a; ERCOT Board *2026 AS Methodology* (Item 15,
9/15/2025); NPRR 1311 (Jan 2026 TAC).
