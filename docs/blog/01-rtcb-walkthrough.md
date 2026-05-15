<!-- Originally published at: https://substack.com/@karthik204653 -->

# What RTC+B Actually Changed: A Visual Walkthrough of the 6-D Action Space

> **Published**: 2026-05-14  
> **GitHub**: [karthikmattu06-hue/ercot-rtcb-bench](https://github.com/karthikmattu06-hue/ercot-rtcb-bench)

---

## Context: How ERCOT Battery Bidding Worked Before December 5, 2025

Before Real-Time Co-optimization Plus Batteries (RTC+B), a battery energy storage
system (BESS) operating in ERCOT participated in two separate, sequential market
processes.

**Day-Ahead Market (DAM)**: The night before, operators submitted energy and ancillary
service (AS) bids. ERCOT cleared energy and AS separately, with no formal mechanism
to enforce energy-AS consistency across a BESS's state of charge (SoC).

**Real-Time Market**: During the operating hour, the ERCOT Security-Constrained
Economic Dispatch (SCED) algorithm dispatched resources to balance load. BESS operators
could submit energy offers and AS capability, but SCED did not co-optimize across
the two — it first set AS awards, then ran SCED for energy given the AS reserves
already held. This sequential approach created **opportunity cost friction**: a BESS
committed to provide regulation service couldn't be fully dispatched for energy
arbitrage even if prices spiked.

The ancillary service products in the pre-RTC+B era were: REGUP, REGDN, RRS (as a
single product), ECRS (added June 2023), and Non-Spin. Five products total.

---

## The Change: What RTC+B Does Mathematically

On December 5, 2025, ERCOT activated RTC+B. The core change is conceptually simple
but computationally expensive:

SCED now co-optimizes energy and ancillary services jointly, with explicit BESS
state-of-charge tracking.

The SCED optimization problem for a single BESS becomes (simplified):

```
maximize: Σ_t [ energy_revenue_t + Σ_as AS_revenue_t,as ]
subject to:
  SoC_t = SoC_{t-1} + η·charge_t - (1/η)·discharge_t          (SoC dynamics)
  SoC_min ≤ SoC_t ≤ SoC_max                                    (SoC bounds)
  energy_t + AS_capacity_reserved_t ≤ power_max                 (power limit)
  AS_capacity_t ≤ AS_demand_curve_max_t                         (ASDC limit)
  SoC_t - duration_constraint_t × AS_capacity_t ≥ SoC_min      (BESS AS feasibility)
```

The last constraint is the key novelty: SCED now checks that the BESS has enough
stored energy to sustain the committed AS capacity for the required deployment
duration, given the current SoC. This is the **ASDC-enforced duration constraint**,
and it couples the energy and AS dimensions in a way the pre-RTC+B market did not.

The optimization is solved as a mixed-integer program (MIP) every ~5 minutes in
real time, across all registered BESS resources simultaneously.

---

## The 6-D Action Space: A Worked Example

Under RTC+B, a BESS operator submits a single bid vector every 5 minutes:

```
a = [energy_mw, regup_mw, regdn_mw, rrs_mw, ecrs_mw, nspin_mw]
```

where energy_mw is signed (positive = discharge, negative = charge), and all AS
components are non-negative capacity offers.

**Worked example**: A 100 MW / 400 MWh (4-hour duration) BESS with current SoC = 60%
(240 MWh available). The operator is considering the following bid at a 5-min interval
where RT energy is at $85/MWh and REGUP MCPC is $3.50/MW:

| Component | Bid value | Revenue |
|-----------|-----------|---------|
| energy_mw | +40 MW discharge | $85 × 40 × (5/60) = $283.33 |
| regup_mw | +50 MW | $3.50 × 50 × (5/60) = $14.58 |
| regdn_mw | +20 MW | (REGDN MCPC) × 20 × ... |
| rrs_mw | 0 | — |
| ecrs_mw | 0 | — |
| nspin_mw | 0 | — |
| **total power** | 40 + 50 + 20 = **110 MW** | **> 100 MW nameplate!** |

This bid is **infeasible** — it violates the power limit constraint (110 MW > 100 MW
nameplate). Under pre-RTC+B, the operator might have tried to submit these separately
and relied on sequential clearing to avoid the conflict. Under RTC+B, the SCED MIP
explicitly enforces the power limit, and the co-optimized solution will reduce one
or more components to satisfy the constraint.

The **feasible** frontier is:
```
|energy_mw| + regup_mw + regdn_mw + rrs_mw + ecrs_mw + nspin_mw ≤ 100 MW
```

This is a 6-D simplex-like feasible region, and the optimal bid point depends on
the current relative prices of all six products — which change every 5 minutes.

---

## Why This Is Hard: Four Asymmetries

### 1. Asymmetric SoC duration constraints

REGUP and RRS require the BESS to be able to *inject* power for a defined duration.
REGDN requires the BESS to be able to *absorb* power. These consume SoC in opposite
directions, and the duration requirements differ (REGUP: typically 30 min; RRS: 10 min).

A BESS near full charge can offer a lot of REGDN but little REGUP. Near empty, the
opposite. The feasible AS offer set changes every 5 minutes as SoC evolves.

### 2. Opportunity cost is multi-dimensional

Committing MW to REGUP reduces the energy export capacity (if prices spike) AND
the RRS capacity (if RRS prices rise). The opportunity cost of each AS product
depends on the joint distribution of all six prices — which under RTC+B are
co-determined by the same optimization clearing them.

### 3. ASDC coupling

The Ancillary Service Demand Curves (ASDCs) set the price that ERCOT is willing
to pay for each MW of AS. Under RTC+B, these curves are used in real time (not
just day-ahead). The AS "demand" is price-inelastic up to the ASDC step, then
drops sharply. This creates non-convex profit curves: the marginal value of
committing the 51st MW of REGUP depends on whether you're above or below the
ASDC breakpoint.

### 4. Non-stationary early-market behavior

The first month of RTC+B was characterized by operators learning — and ERCOT's
algorithm calibrating. AS MCPCs were unusually volatile in December 2025, with
some products clearing near zero and others spiking unexpectedly. On January 8,
2026, ERCOT tightened the SCED MIP optimality gap from ~2% to ~0.5%, reducing
dispatch suboptimality but also changing the price distribution. Any algorithm
trained on data from December 2025 without accounting for this regime change will
have miscalibrated expectations for the Jan–Mar 2026 period.

---

## What This Means for Bidding Algorithms

The benchmark includes four classes of bidding algorithms, each designed to handle
the 6-D action space with different levels of information and compute:

**Perfect-foresight MIP**: Solves the full co-optimization with known future prices.
Sets the theoretical upper bound on revenue. Not deployable, but useful for gap
analysis. **Implemented.** Feb 1–7 2026 result: $178,442 / 7 days (100 MW / 400 MWh
BESS at HB_HUBAVG, Gurobi 13).

**Deterministic MILP (point forecast)**: Uses DAM clearing prices as a point forecast.
Solvable in < 1 second. The "competent human operator with a spreadsheet" baseline.
**Implemented.** Feb 1–7 result: $136,100 / 7 days — **76.3% capture** of perfect
foresight. Run: `python scripts/smoke_milp.py --v01-dir path/to/v0.1`

**Two-stage stochastic MILP**: Accounts for price uncertainty via scenario trees.
More robust but slower. The industry-standard approach for battery bidding. Planned.

**Constraint-aware SAC**: Deep RL (Soft Actor-Critic) with SoC constraints encoded
in the policy network. Learns the 6-D price-action mapping from data. The hypothesis
is that learned policies can capture the ASDC nonlinearities and AS correlations that
are hard to encode in a MILP objective. Planned (NeurIPS 2026 target).

The dataset (`docs/dataset-card.md`) provides the observational foundation for all
four approaches.

---

## Data Preview

The REGUP, RRS, ECRS, and NSPIN MCPCs for January 2026 show the price spikes on
January 8 (MIP tighten) and the persistent near-zero ECRS prices in early January.
Full time-series plots are in the repo's exploratory notebooks.

---

## Next

- Blog post #2 (Week 3): "The MIP Upper Bound: How Much Revenue Are You Leaving
  on the Table?"
- Blog post #3 (Week 5): "Why Deep RL Keeps Running Out of Battery"

The dataset and baseline implementations are open at
`github.com/karthikmattu06-hue/ercot-rtcb-bench`.
