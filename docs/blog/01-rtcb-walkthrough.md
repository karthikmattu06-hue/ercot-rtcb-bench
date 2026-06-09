## How ERCOT Battery Bidding Worked Before December 5, 2025

Before Real-Time Co-optimization Plus Batteries (RTC+B), a battery energy storage system (BESS) in ERCOT participated in two sequential market processes.

**Day-Ahead Market (DAM)**: Operators submitted energy and ancillary service (AS) bids the night before. ERCOT cleared the two separately, without enforcing consistency against a BESS's state of charge (SoC).

**Real-Time Market**: During each operating hour, ERCOT's Security-Constrained Economic Dispatch (SCED) algorithm balanced load by dispatching resources. SCED set AS awards first, then dispatched energy against whatever capacity remained after AS reserves were held back. A BESS committed to regulation couldn't be fully dispatched for energy arbitrage even when prices spiked.

Five AS products existed before RTC+B: REGUP, REGDN, RRS (as a single product), ECRS (added June 2023), and Non-Spin.

---

## What RTC+B Does Mathematically

On December 5, 2025, ERCOT activated RTC+B. SCED now co-optimizes energy and ancillary services jointly, with explicit BESS state-of-charge tracking.

The SCED problem for a single BESS becomes (simplified):
```
maximize: Σ_t [ energy_revenue_t + Σ_as AS_revenue_t,as ]
subject to:
  SoC_t = SoC_{t-1} + η·charge_t - (1/η)·discharge_t          (SoC dynamics)
  SoC_min ≤ SoC_t ≤ SoC_max                                    (SoC bounds)
  energy_t + AS_capacity_reserved_t ≤ power_max                 (power limit)
  AS_capacity_t ≤ AS_demand_curve_max_t                         (ASDC limit)
  SoC_t - duration_constraint_t × AS_capacity_t ≥ SoC_min      (BESS AS feasibility)
```

The last constraint is new. SCED verifies that a BESS holds enough stored energy to sustain its committed AS capacity over the required deployment duration. Energy and AS, which used to clear independently, are now coupled through SoC.

The optimization runs as a mixed-integer program (MIP) every ~5 minutes in real time, across all registered BESS resources simultaneously.

---

## The 6-D Action Space: A Worked Example

Under RTC+B, a BESS operator submits a single bid vector every 5 minutes:

```
a = [energy_mw, regup_mw, regdn_mw, rrs_mw, ecrs_mw, nspin_mw]
```

`energy_mw` is signed (positive = discharge, negative = charge); the AS components are non-negative capacity offers.

**Worked example**: a 100 MW / 400 MWh (4-hour duration) BESS at SoC = 60% (240 MWh available). RT energy is $85/MWh and the REGUP MCPC is $3.50/MW. The operator considers:

| Component | Bid value | Revenue |
|-----------|-----------|---------|
| energy_mw | +40 MW discharge | $85 × 40 × (5/60) = $283.33 |
| regup_mw | +50 MW | $3.50 × 50 × (5/60) = $14.58 |
| regdn_mw | +20 MW | (REGDN MCPC) × 20 × ... |
| rrs_mw | 0 | — |
| ecrs_mw | 0 | — |
| nspin_mw | 0 | — |
| **total power** | 40 + 50 + 20 = **110 MW** | **> 100 MW nameplate** |

This bid is infeasible: 110 MW exceeds the 100 MW nameplate. Before RTC+B, an operator could have submitted these separately and let sequential clearing dodge the conflict. SCED now enforces the power limit explicitly, so the cleared solution scales one or more components down.

The feasible frontier is:
```
|energy_mw| + regup_mw + regdn_mw + rrs_mw + ecrs_mw + nspin_mw ≤ 100 MW
```

This is a 6-D simplex-like feasible region. The optimal bid depends on the relative prices of all six products, which change every 5 minutes.

---

## Why This Is Hard: Four Asymmetries

### 1. Asymmetric SoC duration constraints

REGUP and RRS require the BESS to inject power for a defined duration. REGDN requires it to absorb power. These consume SoC in opposite directions, and the duration requirements differ (REGUP: 30 min; RRS: 10 min).

Near full charge, a BESS can offer plenty of REGDN but little REGUP. Near empty, the reverse. The feasible AS offer set shifts every 5 minutes as SoC evolves.

### 2. Opportunity cost is multi-dimensional

Committing MW to REGUP cuts both energy export capacity (if energy prices spike) and RRS capacity (if RRS prices rise). Each AS product's opportunity cost depends on the joint distribution of all six prices. Under RTC+B, those prices are co-determined by the same clearing that fixes the awards.

### 3. ASDC nonlinearity

The Ancillary Service Demand Curves (ASDCs) set the price ERCOT pays for each MW of AS. RTC+B applies these curves in real time, not just day-ahead. AS demand is price-inelastic up to the ASDC step, then drops sharply. The result is a non-convex profit curve: the marginal value of the 51st MW of REGUP depends on whether you sit above or below the ASDC breakpoint.

### 4. Non-stationary early-market behavior

The first month of RTC+B was messy on both sides. Operators were still learning the new mechanics; ERCOT's algorithm was still calibrating. AS MCPCs ran unusually volatile through December 2025, with some products clearing near zero and others spiking. On January 8, 2026, ERCOT tightened SCED's MIP optimality gap from ~2% to ~0.5%, cutting dispatch suboptimality but also shifting the price distribution. Models trained on December 2025 data without accounting for this regime change will be miscalibrated for Jan–Mar 2026.

---

## What This Means for Bidding Algorithms

The benchmark covers four classes of bidding algorithms, varying in how much they assume about future prices and how much compute they need.

**Perfect-foresight LP**: Solves the full co-optimization with known future prices. Sets the revenue upper bound. Not deployable, but the right anchor for gap analysis.

**Deterministic LP (point forecast)**: Uses DAM clearing prices as a point forecast. Solves in under a second. The floor a competent operator could replicate with a spreadsheet. **It captures a large fraction of the perfect-foresight ceiling; current figures are in the repo.

**Two-stage stochastic LP**: Adds price uncertainty via scenario trees. Slower than deterministic but robust to forecast error. The standard academic approach for storage bidding. Planned.

**Constraint-aware SAC**: Soft Actor-Critic with SoC constraints encoded in the policy. Learns the 6-D price-to-action mapping directly from data. The bet: learned policies can capture ASDC nonlinearities and AS price correlations that are awkward to express in a LP objective. Planned (NeurIPS 2026 target).

The dataset (`docs/dataset-card.md`) is the shared input for all four methods. The repo's exploratory notebooks plot the January 2026 MCPCs, including the January 8 spike and persistent near-zero ECRS prints in early January.

---

## Next

- Blog post #2 : "The MIP Upper Bound: How Much Revenue Are You Leaving on the Table?"
- Blog post #3 : "Why Deep RL Keeps Running Out of Battery"

Dataset and baseline implementations: `github.com/karthikmattu06-hue/ercot-rtcb-bench`.