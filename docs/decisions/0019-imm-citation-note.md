# 0019 — IMM citation resolution note (2025 State of the Market Report)

**Status:** Note (ADR-adjacent, per the 0016 precedent)
**Date:** 2026-08-14

Closes the "fetch-and-verify before citation" open thread carried by ADR 0017 (open
thread 4) and ADR 0018 (open thread 2).

---

## Source

**2025 State of the Market Report for the ERCOT Electricity Markets**, Independent Market
Monitor for ERCOT (Potomac Economics), **May 2026** (cover date; the hosting URL path reads
`/2026/06/`). 175 pages.
URL: https://www.potomaceconomics.com/wp-content/uploads/2026/06/2025-State-of-the-Market-Report-for-ERCOT.pdf

Retrieved and text-extracted 2026-08-14. **Page numbers below are PDF page indices** of the
175-page file; where the printed page label differs it is given in parentheses.

---

## Verified — quotable

### 1. AS over-procurement (VERIFIED, p. 14, Executive Summary)

> "ERCOT's procurement practices raise the AS requirements to more than double the ancillary
> service quantities needed to achieve a reasonable standard of reliability. This includes
> 2 GW of reserves that provide virtually no incremental reliability value in terms of
> reducing the probability of load shed."

Corroborated at p. 59 (chapter-level restatement): "the volume of reserves set by ERCOT's AS
Plan is 140% larger than a 1-in-10 reliability standard for load shed would require."
Related ASDC critique at p. 20 (printed x).

Both the "more than double" phrasing and the "2 GW" figure are present verbatim. **Citable.**

### 2. DAM-vs-RT premium (VERIFIED, p. 14 and p. 163)

Annual, all-market (p. 14):

> "The day-ahead market cleared at a modest premium to the real-time market in 2025."

AS-specific, post-RTC (p. 163, Appendix):

> "Compared to recent trends in convergence for energy between the day-ahead and real-time
> markets, the day-ahead premium for AS has been very high in the early days of RTC. Two
> events account for a disproportionate share of this premium. Excluding RegDown, elevated
> day-ahead market prices on December 5, 2025, and during Winter Storm Fern on January 21-27,
> 2026, account for 57-75% of the average day-ahead market premium for energy and up-reserve
> products."

The same passage adds: "We expect this premium to diminish over the year and to be
significantly lower in the 2026 annual average." **Note this is a forward expectation, not a
measurement**, and does not constitute evidence for the maturation mechanism that ADR 0017 §4
recorded as NOT ESTABLISHED. **Citable, with the annual/early-RTC distinction preserved** —
"modest" describes 2025 overall; "very high" describes AS in early RTC.

### 3. DAM AS awards are financial, not physical (VERIFIED, p. 14; corroborated pp. 59, 162)

> "With the implementation of RTC, day-ahead ancillary service awards no longer represent
> physical obligations to provide reserves in real time. Instead, energy and ancillary
> services in the day-ahead market are now strictly financial positions, and ERCOT settles
> imbalances on those positions in real time." (p. 14)

p. 162: "With the implementation of RTC, AS awards in the day-ahead market now function as
financial positions, like energy awards. Since December 6, 2025, the day-ahead market has
also allowed transactions in virtual AS, i.e., strictly financial positions that are not
associated with any physical resources." **Citable.**

### 4. NSRS-specific mechanism (VERIFIED — both components present, p. 166 (printed A-8) and p. 21)

Both halves of the mechanism appear in the SOM report:

**Procurement beyond plan via ASDC characteristics** (p. 166):

> "From December 5, 2025, through February 2026, ERCOT procured nearly 1,400 MW of NSRS above
> the NSRS plan, on average. Thus, this extension of the ASDC for NSRS effectively increases
> demand for NSRS in the real-time market dispatch model. As discussed in the AS Methodology
> section, the NSRS plan is already vastly oversized, yet the ERCOT real-time market is
> designed to procure even more."

**Duration requirement** (p. 166):

> "Since RTC go-live, NSRS has consistently been more expensive than ECRS and RRS... Two
> factors related to the implementation of RTC have reinforced this trend: 1) the extension of
> the ASDC for NSRS with the excess volume from the AORDC, and 2) the 4-hour duration
> constraint for NSRS."

Standing recommendation 2024-2 (p. 21): "Set Duration Requirement for Non-Spin Reserve Service
(NSRS) to One Hour."

**Consequence:** the Dec 15, 2025 presentation is **no longer the only source** for the
NSRS-specific mechanism. The SOM report can be cited directly, and the secondhand presentation
reference can be dropped from the citation queue.

---

## Discrepancy recorded — Winter Storm Fern date window

The IMM dates Winter Storm Fern as **January 21–27, 2026** (pp. 163, 165, 168 — used
consistently across the premium, AS-shortage, and RUC-commitment analyses). ADR 0017 Exhibit 2
and ADR 0018 use **January 23–26, 2026**, sourced from corroborating coverage and the DOE
emergency-order window, and W7's Fern-exclusion refit excluded exactly those four days.

The IMM window is seven days and is a documentary primary source. Three days the IMM counts as
Fern (Jan 21, 22, 27) **remained in W7's training sample**. W7's sensitivity result is therefore
a *lower bound* on Fern's influence on the fitted parameters, not a full accounting. This does
not change W7's conclusion — the sign pattern was preserved 4/4 and the direction of every
parameter movement is established — but the magnitudes understate the effect. Recorded; no
recomputation performed.

---

## Remaining unverified

- The **Dec 15, 2025 IMM presentation** itself was never retrieved. It is now superseded as a
  citation need (see item 4) and is dropped from the queue rather than resolved.
- No claim in this note rests on any source other than the May 2026 SOM report.

---

## Interpretive note (one sentence, pre-approved)

The post-RTC+B financial (non-physical) nature of DAM AS awards makes a persistent
DAM-over-RT AS premium economically unsurprising as a risk premium — relevant context for the
W5 DAM-anchor findings, recorded here for any future writeup.
