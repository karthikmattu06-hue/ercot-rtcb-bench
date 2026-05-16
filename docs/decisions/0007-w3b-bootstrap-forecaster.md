# ADR 0007: W3-B Bootstrap Probabilistic Forecaster Design

**Status:** Accepted
**Date:** 2026-05-16
**Author:** Karthik Mattu

---

## Context

W3-B requires a probabilistic price forecaster to provide the scenario input for
the stochastic MILP (W3-C) and DFL baseline (W3-D) battery bidding algorithms.
The forecaster must produce a `ScenarioTree` — a set of K joint price trajectories
across 6 price series (LMP + 5 AS MCPCs) at 5-minute resolution for one operating
day — along with probability weights.

Key constraints:
- **Single-regime pool**: The ERCOT RTC+B market launched Dec 5, 2025. A MIP-tighten
  regime change on Jan 8, 2026 significantly altered AS price dynamics. The pool
  must be restricted to post-tighten data (Jan 9, 2026 onward) to avoid mixing
  structurally different regimes.
- **Small pool**: As of Apr 20, 2026 (first backtest day), only ~101 eligible pool
  days exist. The forecaster must work well under small-pool conditions.
- **Joint distribution**: W3-C requires scenarios that capture cross-series dependence
  (e.g., high-load days tend to have both high LMP and high AS prices). Per-series
  independent sampling would destroy this structure.
- **5-minute resolution**: The optimizer runs at SCED granularity; no temporal
  aggregation is acceptable.

## Decision

A **whole-day vector block residual bootstrap** with **analog-day matching** and
**k-medoids scenario reduction** (K=15).

The forecaster has four components:

### 1. Analog-day matching (pool construction)

**Pool**: Jan 9, 2026 through target_day − 1. Hard exclusion of Dec 2025 and
Jan 1–8, 2026 (pre-tighten regime). Minimum pool depth gate: 10 days.

**Day-type filter (hard)**: Match target day type (weekday / weekend / NERC holiday).
Relaxed to all day-types if fewer than 10 days of the target type are available.

**Similarity metric**: z-normalized net-load Euclidean distance on the target day's
288-point profile (net_load_mw = total_load − wind − solar). Z-normalization ensures
load-level differences don't dominate shape similarity.

**N**: Top 40 analog days selected by distance.

**Rationale**: Net load captures the dominant driver of both energy and AS price
variation. Day-type filtering ensures structural similarity (e.g., weekend off-peak
patterns don't pollute weekday analogs). Z-normalization is essential for a growing
pool where early-winter load levels differ significantly from late-spring levels.

### 2. Residual bootstrap (scenario generation)

**Residual**: `residual[t] = RT_price[t] − DAM_price[t]` for each of the 6 series.
Computed for each of the N analog days using that day's actual RT prices and
DAM prices.

**Scenario**: `scenario[t] = DAM_target[t] + residual_analog[t]`. One scenario
per analog day; the DAM prices for the TARGET day are the point forecast.

**Clipping**: AS MCPC series clipped to ≥ 0. LMP is not clipped (negative prices
are valid and informative).

**Rationale**: The residual formulation separates the "what is the market expecting"
(DAM) from "how does the market deviate from expectations" (residual). This gives
K = N ≤ 40 raw scenarios preserving full cross-series and intraday dependence from
each analog day. The DAM price as point forecast is the natural anchor since it
represents the day-ahead consensus.

**Note**: For the Apr 20–26 backtest, target-day net load was obtained from the
active ERCOT load forecast model (InUseFlag=True), not post-settlement actuals,
since post-settlement data lags by ~60 days. This is the correct ex-ante procedure;
future runs against settled dates can use actuals.

### 3. K-medoids scenario reduction (K = 15)

**Algorithm**: Partitioning Around Medoids (PAM) with k-medoids++ initialization.

**Feature space**: [N, 6×288] array; per-series z-normalized before computing
Euclidean distance. This weights each of the 6 series equally regardless of
price scale differences (NSPIN prices are an order of magnitude smaller than LMP).

**K = 15**: Balances scenario tree tractability for the MILP (W3-C) against
distributional fidelity. At K=15, the representative scenarios capture the major
modes of the distribution while keeping the MILP branch count manageable.

**Probability weights**: Proportional to cluster size (fraction of raw scenarios
assigned to each medoid).

**Rationale**: Medoid-based reduction preserves actual observed days as
representatives, avoiding interpolated or extrapolated scenarios. K-medoids++
initialization reduces sensitivity to random seed.

### 4. ScenarioTree contract

The `ScenarioTree` dataclass is the shared interface between:
- **W3-B** (producer): Bootstrap forecaster
- **W3-C** (consumer 1): Stochastic MILP, uses `as_arrays()` for Gurobi
- **W3-D** (consumer 2): DFL baseline, uses `as_tensor(framework="torch")`

Fixed dimensions: K=15 scenarios, 6 series, 288 time steps, 5-min resolution.

## Backtest Findings (Apr 20–26, 2026 — primary panel)

The gate ran with these thresholds: |bias| < 5.0 $/MWh (LMP), < 1.0 $/MW
(RegUp/RegDn/NSPIN), < 0.5 $/MW (RRS/ECRS); 80% coverage > 60%.

| Series | Bias | CRPS | 80% Coverage | Gate |
|--------|------|------|--------------|------|
| LMP | −12.55 $/MWh | 13.50 | 60.2% | ✗ bias |
| MCPC RegUp | +0.86 $/MW | 3.46 | 55.5% | ✗ cov |
| MCPC RegDn | +0.89 $/MW | 1.29 | 48.9% | ✗ cov |
| MCPC RRS | +1.34 $/MW | 3.28 | 52.8% | ✗ bias+cov |
| MCPC ECRS | +1.02 $/MW | 4.01 | 52.7% | ✗ bias+cov |
| MCPC NSPIN | +0.80 $/MW | 8.93 | 47.2% | ✗ cov |

**Findings** (not to be tuned without explicit decision):

1. **LMP negative bias (−12.55 $/MWh)**: The analog pool (Jan 9 – Apr 19) has higher
   average LMP than the Apr 20–26 target window. Apr 25 had a realized spike of $95/MWh
   not well-represented in the pool. This bias reflects the small pool and seasonal
   mismatch — it will naturally reduce as the pool accumulates more late-spring days.

2. **AS MCPC coverage 47–56%**: AS prices in the analog pool (dominated by Jan–Feb 2026)
   were higher and more volatile than Apr 20–26 actuals. The bootstrap produces scenarios
   anchored higher than realized. Combined with k-medoids reduction compressing the
   distribution, 80% intervals are too narrow and too high. This is a structural finding:
   the pool is still too small and too seasonally concentrated to produce well-calibrated
   AS scenarios.

**No immediate tuning is warranted.** As the pool grows through late spring and summer
2026, these biases should decay. If W3-C / W3-D results are highly sensitive to
forecaster calibration, revisit with a larger pool before drawing algorithm conclusions.

## Rejected Alternatives

**Per-series bootstrap**: Drawing residuals independently for each series would have
destroyed the cross-series dependence structure that makes the scenarios useful for
joint dispatch optimization.

**Historical simulation (full days)**: Using raw historical days without DAM anchoring
would confound the "level" of prices with the "shape" — the residual bootstrap
separates these cleanly.

**Parametric distributions (e.g., Gaussian copula)**: Requires estimating a 1728-
dimensional covariance structure (6 × 288) from a small pool (~101 days). Bootstrap
is nonparametric and more robust at small N.

**K > 15**: Tested K=25; MILP solve time increases super-linearly. K=15 was chosen
as the largest K where the MILP remains tractable in real-time (< 60s solve target).

**Season buckets**: An early design used winter/shoulder/summer season buckets to
restrict the pool further. Dropped in favor of the net-load distance metric, which
encodes seasonality implicitly without requiring fixed cutoffs.

## Consequences

- **W3-C / W3-D** consume `ScenarioTree` objects from `BootstrapForecaster.forecast(day)`.
  The API is stable; only metadata fields may be extended.
- **Calibration monitoring**: The backtest gate in `scripts/backtest_w3b.py` should be
  re-run monthly as the pool grows. Findings reported here establish the Apr 2026
  baseline; do not tune the forecaster to chase these metrics — let the pool grow first.
- **Forecaster dataset extension**: `data/processed/forecaster/` now covers
  Jan 9 – May 10, 2026. The assembly pipeline (`scripts/backfill_w3b.py`) uses
  hybridbid processed data as the primary source with API-fetched supplements for
  Apr 16 – May 10. Load data for recent dates uses the active ERCOT 7-day load
  forecast model (InUseFlag=True) as a proxy for post-settlement actuals.
