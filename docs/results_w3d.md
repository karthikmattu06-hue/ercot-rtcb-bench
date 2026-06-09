# W3-D Results: Decision-Focused Learning (DFL) MLP

**Panel:** Apr 20–26, 2026 (168 hours)  
**BESS:** 100 MW / 400 MWh, RTE=0.88  
**Solver:** scipy HiGHS (Gurobi license 2786301 expired)

---

## Five-Method Comparison

| Method | Total ($) | Energy ($) | AS ($) | Term.Liq ($) | vs PF |
|---|---:|---:|---:|---:|---:|
| PF LP (upper bound) | 351,612 | 253,765 | 97,601 | 245 | 100.0% |
| Deterministic LP — DAM | 238,421 | 185,034 | 47,871 | 5,516 | 67.8% |
| Deterministic LP — EV (scen mean) | 250,174 | 168,703 | 73,412 | 8,058 | 71.2% |
| Stochastic LP — scenario tree | 238,376 | 159,021 | 72,478 | 6,878 | 67.8% |
| DFL-MLP → Deterministic LP | 236,591 | 183,289 | 47,899 | 5,403 | 67.3% |

DFL vs DAM deterministic: **−$1,830** (−0.8%)  
DFL vs EV (scenario mean): **−$13,583** (−5.4%)

---

## DFL Training Summary

| Parameter | Value |
|---|---|
| Architecture | 2-layer MLP, hidden_dim=256, dropout=0.1 |
| Feature dim | 419 (calendar + DAM hourly + sys conditions + lag stats) |
| Training horizon | T=12 (1h = committed horizon) |
| QP regulariser ε | 0.1 |
| Training days | 95 (Jan 9 – Apr 13) |
| Val days | 6 (Apr 14–19) |
| Epochs run | 4 (early stop, patience=3) |
| Best epoch | 1 |
| Best val revenue | $29,469 (first-hour across 6 val days) |
| Solver failures | 0/95 training days |

Training val-revenue by epoch:

| Epoch | Val Revenue | Train Loss |
|---|---:|---:|
| 1 ✓ | $29,469 | −576,166 |
| 2 | $28,269 | −574,349 |
| 3 | $12,782 | −479,380 |
| 4 | $10,710 | −321,470 |

Best checkpoint: epoch 1 (first-epoch trained, close to DAM-baseline initialisation).

---

## Contextual Benchmarks

**Mar 15 single-day PF (from diagnostic run, prior session):** $14,092.64  
This day was used for Task 1 (diff-LP verification) and the overfit check. The 24h PF serves as a sanity reference for what daily peak performance looks like under good conditions.

**Panel-level PF ($351,612):** Across 168 hours, average per-hour PF revenue ≈ $2,093.

---

## Interpretation

### Why DFL underperforms the DAM baseline

The core failure mode is a **horizon mismatch**: the model is trained to optimise first-hour (T=12) RT revenue, but at eval time the MLP forecast is fed into a 24-hour LP. The gradient the model learned says "shift this price series so the 1h LP commits more profitable first-hour actions." But that same forecast adjustment changes the 24h LP's SoC carry decisions across 23 subsequent hours, often degrading them.

The result is a model that makes the first-hour decision marginally better (or no worse) but systematically mismanages SoC across the day.

### The DAM-baseline zero-init is a strong prior

The MLP is zero-initialised at the output layer, making the initial forecast exactly equal to the DAM prices. The DAM LP at 67.8% of PF is already the single strongest easily-computable baseline. DFL in this configuration doesn't improve on it — but it also doesn't fail catastrophically (−0.8% gap).

### What would be needed for DFL to outperform

1. **T=288 training horizon**: match the eval horizon. Requires replacing SCS with ECOS or a custom KKT differentiation — SCS cannot solve the 288-step SoC chain accurately.
2. **More training data**: 95 days is small; the model overfit in epoch 2.
3. **SPO+ loss**: avoids implicit differentiation entirely, compatible with exact LP solvers.

### Stochastic LP note

The stochastic LP ($238,376) continues to underperform the EV baseline ($250,174) in aggregate, consistent with the W3-C finding. DFL is even further below stochastic, ruling out the hypothesis that DFL provides "free" multi-scenario information.

---

## Engineering Notes

- **Per-unit reformulation (ADR 0009):** Physical-unit SCS produced violations up to 34 MWh. Per-unit (all variables ∈ [0,1]) achieved constraint violations < 1e-7 MW.
- **T_TRAIN = 12 (not 72):** SCS (ADMM) fails to converge for T≥24 on real ERCOT prices due to the long SoC dynamics equality chain. T=12 converges cleanly at ε=0.1.
- **NaN RT prices:** 14/95 training days had NaN in AS price columns (zero-filled); the eval period had sporadic NaN in RT settlement prices (zero-filled).
- **Gurobi license expired:** All LP solves use scipy/HiGHS fallback. Eval runtime: 71.5s for 168 hours.
