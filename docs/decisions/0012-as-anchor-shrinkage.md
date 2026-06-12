# ADR 0012 — Scarcity-conditioned DAM AS anchor shrinkage (W5-A)

**Status:** Accepted
**Date:** 2026-06-11

---

## Context

W4 attribution (ADRs 0010/0011) measured the AS effective-price leg (ΔAS) at
**+$36,393** on the Apr 20–26 eval panel — the largest *bankable* lever in the v0.2
ordering. That figure is an **oracle bound** (forecast → oracle E[max] effective
prices), not a capturable estimate. W5-A's diagnostic (`results_w5a_diagnostic.md`)
established the error structure:

- The v0.1 AS "forecaster" is not a model — AS prices are the **DAM AS MCPC anchor**
  plus net-load-analog (RT−DAM) residuals from the shared whole-day bootstrap,
  clipped ≥0, no jitter. Analog selection keys on net load only.
- The AS forecast is systematically **over-forecast** on all products, and the error
  is **scarcity-concentrated, not a flat level bias**: ~97–100% of the
  revenue-weighted bias sits in the top decile of intervals (high net-load / high
  LMP); calm hours are ≈ 0. The bias originates in the **DAM anchor** (bias_dam ≈
  bias_eff); RegDn is flat everywhere.

The diagnostic's implication: a flat debias is the wrong rung; the cheap lever is
**scarcity-state-conditioned**. This ADR records the correction, its eval result, and
the (substantial) hedges around it.

---

## Decision

A **4-parameter, per-product, two-regime multiplicative shrinkage of the DAM AS
anchor**, conditioned **only on the DAM AS quote level** (ex-ante by construction —
no realized LMP, net load, or any forecast-time-unavailable quantity).

Per product p ∈ {regup, rrs, ecrs, nspin} (**RegDn and LMP untouched**):

```
quote ≤ τ_p  → unchanged              (calm hours; Q1–Q3 bias ≈ 0, do not touch)
quote > τ_p  → τ_p + s_p·(quote − τ_p)
```

- **τ_p = train q90** of the DAM AS quote (Jan 23–Apr 13). 5-min and hourly q90 are
  identical to < $0.003 (DAM ffill replicates each hourly quote 12×).
- **s_p** fit by **method of moments**: choose s_p so the mean high-regime E[max]
  effective bias on train is driven to ~0. One parameter per product, 4 total. If the
  moment condition gives s_p < 0, clamp to 0.
- Applied in `forecaster/bootstrap.py:build_raw_scenarios` **before** residual
  addition and the ≥0 clip, so the bootstrap scenarios and the E[max] price the
  stochastic LP plans on both inherit it. Implemented behind an `ASAnchorCorrection`
  flag; **with the flag off the v0.1 baseline reproduces exactly** ($238,376.27).

Fitted parameters (train):

| Product | τ_p | s_p | high-regime E[max] bias: uncorrected → after |
|---|---:|---:|---:|
| regup | 3.56 | 0.152 | +18.45 → −0.00 |
| rrs | 2.71 | 0.001 | +23.25 → +0.00 |
| ecrs | 2.56 | 0.038 | +24.79 → −0.00 |
| nspin | 14.98 | 0.000 (clamped) | +47.66 → +2.04 |

The fit was performed on a faithful analog-level reconstruction of the bootstrap and
**verified through the deployed k-medoids forecaster** (high-regime bias → ~0,
low-regime unchanged).

---

## Consequences

### Eval result (Apr 20–26, Gurobi)

| | Total | Energy | AS | Liq |
|---|---:|---:|---:|---:|
| Baseline (flag off) | $238,376.27 | 159,021 | 72,478 | 6,878 |
| Corrected | $256,647.66 | 172,516 | 76,425 | 7,707 |
| **Δ** | **+$18,271** | +13,495 | +3,947 | +829 |

**ΔW5A = +$18,271 = 50.2% of the $36,393 oracle bound**, on a single one-week panel.

### Mid-gate (val Apr 14–19) — passed

High-regime over-forecast shrank in magnitude for all four products, sign-consistent
(regup +3.78→+2.01, rrs +3.20→+1.37, ecrs +4.32→+1.53, nspin +14.55→+11.14);
low-regime bias moved ≤ $0.021/MW (no-harm; correction is identity on calm hours).

### Mechanism — reallocation, not reduction

The realized mechanism is a **reallocation**: energy **+$13.5k** *and* AS **+$3.9k**
both rose. The baseline mis-committed AS capacity into scarcity hours where the
forecast scarcity **did not materialize** in realized MCPC; correcting the perceived
AS price there lets the LP both capture the coincident high-LMP energy arbitrage and
place AS more profitably. This is *not* "less AS commitment → AS revenue down" — total
realized AS revenue increased. (All three revenue components rose; per *day* it did
not — see the Concentration hedge.)

### Concentration hedge (mandatory)

The net gain is **driven by a single scarcity day**: Apr 25 contributes +$18.7k of the
+$18.3k panel total. The recovery is **not monotone** — Apr 24 (−$5.5k) and Apr 22
(−$1.2k) are loss days where the shrinkage led the LP into a worse trade on that day's
realized path. The correction is therefore **sign-uncertain on calm weeks**, and
carries a **symmetric risk**: by shrinking the AS anchor it will *under-commit* AS in
weeks where scarcity *does* realize at high MCPC. The 50.2% figure should be read as a
one-week point estimate with material variance, not a stable expectation.

### PF sanity

PF = $351,612 is **unchanged by construction** — `perfect_foresight` settles on
realized RT prices and never calls `BootstrapForecaster`; the correction cannot reach
it.

---

## Open threads

- **nspin anchor over-quote.** nspin's DAM quote exceeds realized MCPC *even at its own
  q90 threshold* — s_p clamps to 0 (pin to τ) yet a +$2.04/MW high-regime residual
  bias remains. This is an **anchor-level problem beyond shrinkage** (the DAM nspin
  price is structurally high relative to RT); a level/threshold correction cannot fully
  fix it. Candidate for a deeper nspin-specific anchor treatment.

- **Second-panel replication is REQUIRED** (promoted from optional) before this lever is
  claimed in the v0.2 roadmap or preprint. The single-scarcity-day concentration and
  the two loss days make one panel insufficient evidence. Minimum: one additional week
  **containing a scarcity day**; a calm week is additionally informative (it tests the
  sign-uncertainty / under-commitment risk directly).

---

## Consequences for the v0.2 ordering (updates ADR 0011)

The AS effective-price lever is now **partially banked at 50.2% recovery** ($18,271 of
$36,393). The **remaining ≈ $18.1k** (bound − realized) is **unattributed**; candidate
contributors include the **nspin anchor residual**, **AS distribution realism** (W4-B),
and the **panel variance evident in the loss days** — none measured here, and a
quote-level shrinkage addresses none of them. The next bankable lever is the **LMP
evening-peak mean fix (~$21.5k, W4-A ΔLMP)** → **W5-B**.

---

## Out of scope (this chunk)

- The nspin deeper anchor fix and AS scenario-family change (W4-B) — separate rungs.
- Cross-panel validation (required next, per Open threads).
- Any LMP-side correction (W5-B).
