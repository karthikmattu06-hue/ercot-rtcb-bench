# W5-A Results: DAM AS Anchor Scarcity-Shrinkage (Phase 2 + 3)

**Scope:** the scarcity-conditioned AS anchor correction motivated by the W5-A
diagnostic (`results_w5a_diagnostic.md`). Fit on train, gated on val, run on the
locked eval panel. No ADR yet (drafting deferred to review).
**Solver:** Gurobi. **Seed:** 42. **Quantity:** Stochastic-LP realized revenue vs
the $238,376 baseline. **Oracle bound:** W4-A ΔAS = $36,393.

---

## The correction (4 parameters, ex-ante)

Per product p ∈ {regup, rrs, ecrs, nspin} (RegDn and LMP untouched), the **DAM AS
anchor** is shrunk *before* residual addition and the ≥0 clip, in
`bootstrap.py:build_raw_scenarios` (behind `ASAnchorCorrection`; baseline = correction
disabled):

```
quote ≤ τ_p  → unchanged
quote > τ_p  → τ_p + s_p·(quote − τ_p)
```

Conditioning is on the **DAM AS quote level itself** — ex-ante by construction (no
realized LMP / net load). τ_p is a fixed train quantile; the single fitted parameter
per product is s_p.

---

## Phase 2 — Fit (train Jan 23–Apr 13, 81 days)

### Thresholds τ_p = q90 DAM quote

| Product | τ (5-min) | τ (hourly) | Δ |
|---|---:|---:|---:|
| regup | 3.560 | 3.560 | 0.0000 |
| rrs | 2.710 | 2.707 | 0.0030 |
| ecrs | 2.560 | 2.557 | 0.0030 |
| nspin | 14.980 | 14.980 | 0.0000 |

5-min vs hourly q90 are identical to < $0.003 — DAM ffill replicates each hourly
quote 12×, so the quantile is invariant. (Reported per spec; immaterial.)

### Fitted s_p (method of moments: drive high-regime E[max] bias → 0)

| Product | s_p | reason | high-regime bias: uncorrected → after |
|---|---:|---|---:|
| regup | 0.152 | ok | +18.45 → −0.00 |
| rrs | 0.0013 | ok | +23.25 → +0.00 |
| ecrs | 0.038 | ok | +24.79 → −0.00 |
| nspin | 0.000 | **clamped** | +47.66 → +2.04 |

The uncorrected high-regime effective over-forecast is enormous (+$18–48/MW).
rrs/ecrs need near-total shrinkage (s ≈ 0, pin to τ); regup a moderate 0.15; **nspin
clamps at s=0** — even pinning the anchor to its own q90 ($14.98) still leaves +$2.04
over-forecast, i.e. nspin DAM is so over-quoted that the threshold itself sits above
realized. Reported, not engineered around (the floor is τ; we do not push below it).

### Train-verify through the real (k-medoids) forecaster

The fit uses a faithful analog-level reconstruction; verifying through the actual
deployed forecaster confirms it transfers:

| Product | high-bias base → corr | low-bias base → corr |
|---|---:|---:|
| regup | +18.45 → **−0.02** | +0.04 → +0.04 |
| rrs | +23.25 → **−0.01** | +0.19 → +0.19 |
| ecrs | +24.77 → **−0.02** | +0.01 → +0.01 |
| nspin | +47.66 → **+2.05** | +1.11 → +1.11 |

High-regime bias driven to ~0 (nspin to its clamped floor); **low-regime unchanged**
(no-harm holds through the real pipeline, including the clip interaction).

---

## Phase 2 — VAL MID-GATE (Apr 14–19, frozen params) — PASSED

| Product | high base → corr (n_hi) | low base → corr (Δ) |
|---|---:|---:|
| regup | +3.78 → +2.01 (168) | +0.081 → +0.063 (−0.018) |
| rrs | +3.20 → +1.37 (240) | +0.164 → +0.171 (+0.007) |
| ecrs | +4.32 → +1.53 (240) | +0.239 → +0.252 (+0.013) |
| nspin | +14.55 → +11.14 (132) | +0.993 → +1.013 (+0.021) |

- **Directional improvement:** high-regime over-forecast shrinks in magnitude for all
  four products, sign-consistent (no flip to under-shoot). Val is calm April, so the
  residual stays positive (params are train-fit) — directional improvement suffices.
- **No-harm:** low-regime bias moves by ≤ $0.021/MW (threshold $0.05) — the correction
  is effectively identity on calm hours, as designed.

**GATE PASSED.**

---

## Phase 3 — Eval panel (Apr 20–26, Gurobi)

| | Revenue | Energy | AS | Liq |
|---|---:|---:|---:|---:|
| Baseline (correction off) | **$238,376.27** | 159,021 | 72,478 | 6,878 |
| Corrected | **$256,647.66** | 172,516 | 76,425 | 7,707 |
| **Δ** | **+$18,271.39** | +13,495 | +3,947 | +829 |

- Baseline reproduces **$238,376.27** (drift +$0.00) with the correction disabled —
  the harness and the forecaster flag are clean.
- **ΔW5A = +$18,271.39 → 50.2% of the $36,393 oracle bound.** Half the oracle-bounded
  AS lever is captured by a 4-parameter, ex-ante correction.

### Mechanism (confirmed, with a caveat)

Energy is the dominant gain (**+$13,495**): lowering the AS price the LP perceives in
scarcity hours stops it over-committing AS capacity there, freeing the battery for the
high-LMP energy arbitrage that coincides with scarcity — exactly the diagnostic's
prediction. **But AS revenue *rose* (+$3,947), not fell** as a naive energy-for-AS
swap would suggest: the baseline was mis-allocating AS into scarcity hours where
realized MCPC is low (the over-forecast), so the reallocation improved *both* margins.
The clean "AS down" half of the predicted mechanism does not hold; the reallocation is
Pareto-improving here.

### Per-day Δ (energy + AS; liquidation is panel-level)

| Day | Δ (E+AS) | energy | AS |
|---|---:|---:|---:|
| 2026-04-20 | +$1,420 | +793 | +627 |
| 2026-04-21 | +$995 | +1,013 | −18 |
| 2026-04-22 | **−$1,155** | −1,328 | +173 |
| 2026-04-23 | +$1,035 | +972 | +62 |
| 2026-04-24 | **−$5,524** | −5,958 | +433 |
| 2026-04-25 | **+$18,694** | +16,067 | +2,627 |
| 2026-04-26 | +$1,978 | +1,936 | +42 |

Recovery is **heavily concentrated on Apr 25** (+$18.7k — the panel's scarcity day),
confirming the diagnostic's prediction that the lever lives in scarcity states. It is
**not monotone**, though: Apr 24 (−$5.5k) and Apr 22 (−$1.2k) are losses where the
shrinkage led the LP into a worse energy/AS trade on that day's realized path. Net
across the panel remains strongly positive (+$18.3k incl. +$829 liquidation).

### PF sanity

PF = **$351,612 unchanged by construction** — `perfect_foresight` settles on realized
RT prices and never calls `BootstrapForecaster`, so the anchor correction cannot reach
it. No re-run needed; if PF had moved, the correction would have leaked.

---

## Summary

A 4-parameter, ex-ante DAM AS anchor shrinkage — conditioned only on the DAM quote
level, RegDn and LMP untouched — captures **50.2% ($18,271) of the $36,393 W4-A ΔAS
oracle bound** on the eval panel, with the gain concentrated on the scarcity day as
predicted. The mid-gate held out of sample; the baseline remains exactly reproducible
with the correction disabled. The recovery is not monotone across days (two loss days),
and nspin's anchor is over-quoted even at its q90 floor (s clamped to 0, +$2/MW residual)
— both are findings for the ADR/cross-panel discussion, not failures.

**Files:** correction `forecaster/bootstrap.py` (`ASAnchorCorrection`) +
`forecaster/forecaster.py`; harness `scripts/backtest_w5a_eval.py`; audit
`data/audit/w5a_eval.json`.

**HARD STOP** — ADR 0012 drafting and merge to `main` await chat review.
