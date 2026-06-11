# W5-A Results: AS Effective-Price Diagnostic (Recon + Phase 0 + Phase 1)

**Scope:** reconnaissance + reproduction gate + bias diagnostic ONLY. No fix
(Phase 2 authorized separately). Eval panel (Apr 20–26) untouched.
**Solver:** Gurobi (license active). **Seed:** 42 (per-day RNG, ADR 0007).
**Script:** `scripts/diagnose_w5a_as.py` · **Audit:** `data/audit/w5a_diagnostic.json`

---

## Phase R — Reconnaissance

### 1. What is the v0.1 AS forecaster?

**There is no dedicated AS forecasting model.** AS prices are produced by the same
**DAM-anchored whole-day vector block bootstrap** that produces LMP
(`BootstrapForecaster`). For each product the forecast is:

```
point forecast (AS)  = DAM AS MCPC for the target day        (day-ahead anchor)
scenario_k (AS)      = DAM_target_AS + (RT_analog_k − DAM_analog_k),  clipped ≥ 0
```

| Property | Finding |
|---|---|
| Model family | DAM AS MCPC anchor + analog RT−DAM residual bootstrap (no regression, no learned model) |
| Per-product vs shared | **Shared** — all 6 series ride the *same* analog days; the [6×288] residual block is indivisible. Per-product info enters only via each product's own DAM anchor and its own residuals. No per-product model. |
| Feature inputs | Analog selection keys on **net-load profile only** (z-normalized daily net load + day-type hard filter). AS prices, load level, wind, solar, DAM — none drive analog selection except net load. |
| Horizon / resolution | Whole operating day, 288 × 5-min. DAM is hourly, forward-filled to 5-min; residuals at 5-min. |

So AS skill is entirely inherited from (a) the **DAM AS price** as anchor and (b)
whatever RT−DAM residual the **net-load-matched** analog days happen to carry.

### 2. Scenario generation → E[max] effective price

- **Residual bootstrap** (`bootstrap.py`): residual = RT_analog − DAM_analog over the
  whole [6×288] block; scenario = DAM_target + residual. **LMP** gets additive
  Silverman jitter; **AS gets none** (both jitter forms were rejected — ADR 0007).
  AS is **clipped at 0** at construction. Reduced to K=15 via recency-weighted
  (H=45d) k-medoids; probabilities sum to 1.
- **E[max] in the LP** (`stochastic_lp.py`): stage-2 uses per-scenario AS awards with
  `lb=0`, so the LP plans on `E_k[max(price,0)]`. Because the non-negativity clip is
  applied at scenario construction, the forecaster's probability-weighted scenario
  mean **already equals** the E[max] effective price the LP optimizes on (δ=0
  baseline). There is no clip-divergence at the forecast layer (the W4-A oracle moved
  the effective price via the δ retarget, not via a different clip).

### 3. File map (and the Phase-2 seam)

| Component | Path |
|---|---|
| Forecaster orchestration | `src/ercot_rtcb_bench/forecaster/forecaster.py` (`BootstrapForecaster.forecast`) |
| Analog matching (net-load only) | `src/ercot_rtcb_bench/forecaster/analog.py` (`match_analogs`) |
| **Scenario generation — Phase-2 seam** | `src/ercot_rtcb_bench/forecaster/bootstrap.py` (`build_raw_scenarios`, AS anchor `dam_target[1:6]` + residual + clip, ~lines 133–140) |
| Data / DAM AS source | `src/ercot_rtcb_bench/forecaster/data_loader.py` (`dam_mcpc_*` ← hybridbid `dam_as_*` / forecaster `dam_prices` parquet) |
| E[max] consumer (LP) | `src/ercot_rtcb_bench/methods/stochastic_lp.py` (stage-2 objective) |
| DAM-deterministic baseline (same DAM AS) | `src/ercot_rtcb_bench/methods/point_forecast.py` |

A corrected AS forecast plugs in at **`bootstrap.py:build_raw_scenarios`** — either
correct the `dam_target` AS anchor before adding residuals, or post-adjust the AS
scenarios (state-conditioned).

**Flagged surprises:** (a) no dedicated AS model — analog selection ignores AS
entirely (net load only); (b) AS receives no jitter (near-deterministic — ties to the
W4-B coverage ceiling); (c) the systematic over-forecast originates in the **DAM AS
anchor** (bias_dam ≈ bias_eff below), not the bootstrap.

---

## Phase 0 — Reproduction gate

| | Value |
|---|---:|
| Baseline Stochastic LP (no oracle) | **$238,376.27** |
| Expected (`backtest_w4b.json`) | $238,376.27 |
| Drift | **+$0.002** (sub-cent; tol ±$1.00) |
| Solver | **Gurobi** (active) |

Components: Energy $159,021 / AS $72,478 / Liq $6,878 — matches the W3-D/W4 table.
**GATE PASSED** under Gurobi; the $238,376 anchor is solver-stable.

---

## Phase 1 — AS forecast bias diagnostic

Train window: **Jan 23 – Apr 13, 2026** (81 days, 23,012 finite intervals/product).
Val preview: Apr 14–19 (6 days). Eval untouched. `bias = forecast − realized` ($/MW-h);
`F_eff` = E[max] effective forecast; `F_dam` = raw DAM anchor.

### Overall bias (train) — over-forecast on every product

| Product | bias_eff | bias_dam | ratio_eff (F/R) | mean F_eff | mean realized | top-decile share |
|---|---:|---:|---:|---:|---:|---:|
| regup | +1.90 | +2.12 | 2.24× | 3.44 | 1.54 | 98.6% |
| regdn | +0.23 | +0.19 | 1.21× | 1.36 | 1.13 | 96.6% |
| rrs | +2.53 | +2.85 | **5.62×** | 3.07 | 0.55 | 99.8% |
| ecrs | +2.51 | +2.62 | **4.39×** | 3.26 | 0.74 | 99.9% |
| nspin | +3.32 | +3.86 | 2.53× | 5.48 | 2.16 | 99.7% |

Every product is **over-forecast** (positive bias), by 1.2×–5.6× in the mean. `bias_dam ≈
bias_eff` (DAM slightly worse) → the error is **in the DAM AS anchor**; the analog
residuals shave it slightly but do not fix it.

### Bias by realized-LMP quartile (scarcity proxy), bias_eff

| Product | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---:|---:|---:|---:|
| regup | +0.37 | +0.41 | +0.19 | **+6.62** |
| regdn | +0.01 | +0.49 | +0.39 | +0.03 |
| rrs | +0.43 | +0.54 | +0.34 | **+8.80** |
| ecrs | +0.32 | +0.37 | +0.10 | **+9.27** |
| nspin | +1.71 | +2.62 | +0.33 | **+8.61** |

### Bias by net-load quartile, bias_eff

| Product | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---:|---:|---:|---:|
| regup | −0.32 | +0.12 | +0.31 | **+7.49** |
| regdn | +0.18 | +0.50 | +0.21 | +0.05 |
| rrs | −0.18 | +0.29 | +0.47 | **+9.52** |
| ecrs | −0.30 | +0.37 | +0.55 | **+9.43** |
| nspin | −1.34 | +0.78 | +0.39 | **+13.43** |

The over-forecast is **almost entirely a high-net-load / high-LMP (scarcity) state
phenomenon.** Q1–Q3 are near zero (even mildly negative for nspin/regup at low net
load); Q4 explodes to +$7–13/MW. **RegDn is the lone exception** — flat ≈ 0 across all
states (down-regulation does not spike in scarcity).

### Error concentration (item 4)

Revenue-weighted absolute bias `|F_eff − R|·max(realized_MCPC,0)`: the **top decile of
intervals holds 96.6%–99.9%** of the total. This is *more* concentrated than the W4-A
LMP evening-peak finding. Peak hour-of-day bias lands at **HoD 13–14 UTC (≈8–9 am CDT,
the morning net-load ramp)** — regup +13.3, rrs +15.0, ecrs +15.2, nspin +8.4 — *not*
the LMP evening peak (HoD 0–1 UTC). AS and LMP errors are concentrated at **different**
times of day.

### Effective-price view & non-negativity (item 3)

`F_eff` (the E[max] effective price the LP plans on) is reported alongside `F_dam`
above; the two track closely. The non-negativity clip binds heavily in **low-price /
overnight** intervals (scenario cells pinned at the 0 floor: 16%–74% by hour, highest
for rrs/ecrs), but is **inactive in the scarcity hours that carry the bias** — so the
scarcity over-forecast is a genuine DAM-anchor level error, **not** a clipping artifact
(distinct from the W4-B AS coverage/clip issue).

### Out-of-sample stability (val, Apr 14–19)

| Product | bias_eff | bias_dam | ratio_eff |
|---|---:|---:|---:|
| regup | +0.44 | +0.54 | 1.49× |
| regdn | +0.51 | +0.49 | 1.58× |
| rrs | +0.59 | +0.83 | 3.73× |
| ecrs | +0.81 | +0.87 | 3.23× |
| nspin | +2.03 | +2.24 | 2.65× |

Same sign, same ordering (nspin largest, rrs/ecrs high ratio), out of sample.
Magnitudes are smaller — April is calmer than the Jan–Apr train span (fewer scarcity
days), consistent with a scarcity-concentrated error.

---

## Answer to the key question

**The AS forecast error is a scarcity-concentrated, state-dependent over-forecast — not
a flat correctable level bias.**

- **Direction:** the forecaster *over-predicts* AS prices on all five products
  (consistent with W4-A's "FC mean > RT mean for all 5 products"). The over-forecast
  is what made the W4-A ΔAS oracle worth +$36,393: the LP commits AS capacity where it
  *thinks* AS pays, and those are exactly the high-net-load scarcity hours where the
  forgone energy arbitrage is most valuable.
- **Structure:** ~97–100% of the revenue-weighted error sits in the top decile of
  intervals, concentrated in **high-net-load / high-LMP** states (Q4) and the **morning
  ramp (HoD 13–14 UTC)**. Q1–Q3 are ≈ 0.
- **Origin:** the bias lives in the **DAM AS anchor** (bias_dam ≈ bias_eff); the
  net-load-analog residual bootstrap does not correct it, and cannot — analog selection
  never looks at AS or scarcity.
- **Implication for the fix (Phase 2, not authorized here):** a **flat per-product
  debias is the wrong rung** — it would barely move the top decile and could hurt the
  near-zero Q1–Q3 calm hours. The cheapest lever that captures a meaningful fraction is
  **scarcity-state-conditioned**: shrink/correct the DAM AS anchor toward realized in
  high-net-load / high-price states (or condition the forecast on a scarcity regime).
  RegDn needs no correction.

**HARD STOP** — Phase 2 (debias vs feature regression vs ASDC structural prior) is
deferred to a separate authorized chunk.
