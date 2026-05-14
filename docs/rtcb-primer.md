# RTC+B Primer: ERCOT's Real-Time Co-optimization Plus Batteries

> **Stub** — this document will be expanded in Week 2 from blog post #1.
> See `docs/blog/01-rtcb-walkthrough.md` for the draft.

## What is RTC+B?

ERCOT's Real-Time Co-optimization Plus Batteries (RTC+B) is a market design
change that went live on December 5, 2025. It integrates battery energy storage
systems (BESS) more directly into the real-time security-constrained economic
dispatch (SCED), allowing BESS operators to submit 6-dimensional bids covering
both energy and five ancillary service (AS) products simultaneously.

## Key changes from pre-RTC+B

- **Co-optimized dispatch**: SCED now jointly optimizes energy and AS
  procurement across BESS resources, replacing the sequential clearing process
- **6-D action space**: Each BESS submits a bid covering energy (buy/sell),
  REGUP, REGDN, RRS, ECRS, and NSPIN simultaneously
- **ASDC integration**: Ancillary Service Demand Curves (ASDCs) are used in
  real-time (not just DAM), creating interdependencies between AS products
- **SoC-aware dispatch**: ERCOT's SCED now tracks state-of-charge constraints
  for registered BESS resources

## Data products affected

See `docs/dataset-card.md` for the full schema and coverage details.

## References

- ERCOT NPRR (Nodal Protocol Revision Request) filing for RTC+B
- ERCOT RTC+B Implementation Guide (public, ercot.com)
