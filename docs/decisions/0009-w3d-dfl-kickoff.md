# ADR 0009 — W3-D: Decision-Focused Learning (DFL) MLP Forecaster

**Status:** Accepted  
**Date:** 2026-06-09

---

## Context

W3-C established LP-based rolling dispatch under three forecast regimes (DAM-deterministic, EV of scenario mean, stochastic). The next question is whether end-to-end training of the forecaster on decision regret — rather than CRPS or RMSE — can push the LP above the EV baseline.

W3-D is a proof-of-concept: a 2-layer MLP is trained to minimise `−first_hour_RT_revenue` by differentiating through a LP-regularised as a QP (cvxpylayers + SCS). At eval time the MLP forecast replaces DAM prices as the 24h LP lookahead; the LP structure is unchanged.

---

## Decisions

### 1. MLP architecture

2-layer MLP, hidden_dim=256, dropout=0.1, zero-initialised output (residual ≈ 0 warm-start).  
Input: FEATURE_DIM=419 (calendar 11 + DAM hourly 144 + system conditions 96 + 7-day lag stats 168).  
Output: 6×288 price residual added to the DAM broadcast baseline.

### 2. Differentiable LP layer — per-unit formulation

The BESS LP becomes a QP by adding `ε·‖actions‖²` to the objective, enabling non-zero KKT gradients.  
**Per-unit reformulation is mandatory for SCS convergence.** Physical-unit variables (d ∈ [0,100] MW, s ∈ [0,400] MWh) produced "Solved/Inaccurate" with SoC violations up to 34 MWh. Normalising all decision variables to [0,1]:
```
d_pu = d / P,  s_pu = s / E,  a_*_pu = a_* / P
ratio = dt * P / E
```
eliminates the mixed-scale conditioning problem. All constraint coefficients are O(1).

### 3. Training horizon T_TRAIN = 12 (1h, not 6h)

The original spec targeted T_TRAIN=72 (6h). SCS (ADMM) fails to converge for T≥24 on any real ERCOT price series: the 72-step equality chain for SoC dynamics is poorly conditioned for first-order methods, producing violations of 34–200 MWh regardless of per-unit scaling. T=12 (1h = committed horizon) converges cleanly (violations < 1e-7 MW) and matches the settlement window exactly — no inter-hour look-ahead during training, but eval uses the full 24h Gurobi LP unchanged.

### 4. QP regulariser ε = 0.1 (not 1e-3)

At ε=1e-3 the QP solution barely moves from the LP vertex (gradient norm ≈ 0.02, essentially no signal). At ε=0.1 SCS still converges and the gradient norm is ~730 (clipped to 1.0 by `clip_grad_norm`). Revenue gap between QP and LP at ε=0.1 is 0.0% for the verification day ($3961.42 vs $3962.00).

### 5. Training protocol

- Online Adam, one step per day, lr=1e-3, weight_decay=1e-5, clip_grad_norm=1.0
- 95 train days (Jan 9 – Apr 13), 6 val days (Apr 14–19)
- Early stopping: patience=3 on first-hour val revenue
- SoC fixed at s0=200 MWh per day (PoC simplification — no cross-day carry)
- NaN RT prices zero-filled (`nan_to_num`) — 14/95 training days had NaN in AS markets

---

## Consequences

### Training outcome

Best checkpoint = epoch 1 (val_rev $29,469 across 6 val days). Epochs 2–4 degrade; early stop fires at epoch 4. The DAM-baseline initialisation is already strong; one epoch of DFL gradient moves slightly improves val performance, but further epochs overfit the 95-day training set.

### Eval results (Apr 20–26, 168 hours)

| Method | Total | Energy | AS | Term.Liq | vs PF |
|---|---:|---:|---:|---:|---:|
| PF LP (upper bound) | $351,612 | $253,765 | $97,601 | $245 | 100.0% |
| Deterministic LP — DAM | $238,421 | $185,034 | $47,871 | $5,516 | 67.8% |
| Deterministic LP — EV | $250,174 | $168,703 | $73,412 | $8,058 | 71.2% |
| Stochastic LP | $238,376 | $159,021 | $72,478 | $6,878 | 67.8% |
| **DFL-MLP → Det LP** | **$236,591** | **$183,289** | **$47,899** | **$5,403** | **67.3%** |

DFL underperforms the DAM-deterministic baseline by −$1,830 (−0.8%) and underperforms EV by −$13,583 (−5.4%).

### Candidate causes

#### (1) Primary — T=12 horizon mismatch

The training horizon (T=12, 1h) does not match the eval horizon (T=288, 24h). The DFL model learns to shift the first-hour price forecast to favour actions that improve first-hour RT settlement. But those same forecast adjustments propagate into the full 24h LP lookahead at eval time and degrade the inter-hour SoC management decisions.

In short: **the model is trained to optimise a 1-hour horizon but deployed on a 24-hour horizon**, and the learned forecast biases are misaligned with the longer planning problem.

A model that could be trained on T=288 would learn forecast adjustments appropriate for the 24h LP. That requires a solver that handles long SoC chains — ECOS, HiGHS, or a direct KKT implementation — which is out of scope for this PoC.

#### (2) Secondary — ε=0.1 train/eval regularisation mismatch

ε=0.1 introduces a secondary train/eval mismatch beyond the horizon issue. The QP regulariser biases training-time solutions toward smaller action norms, while the eval LP (ε=0) dispatches at corners. Forecasts learned to be optimal inputs to the regularised QP may not be optimal inputs to the un-regularised 24h LP. The earlier verification's action-norm divergences (sub-MW on energy at non-degenerate vertices, larger on AS at degenerate vertices) confirm the mechanism is active in this problem; we cannot cleanly attribute fractions of the realised shortfall to T=12 vs. ε=0.1 without controlled ablations, which are out of PoC scope.

#### (3) Supporting — DAM-gap vs EV-gap decomposition

The DFL-vs-DAM gap (−$1,830, −0.8%) and the DFL-vs-EV gap (−$13,583, −5.4%) tell different parts of the story. The DAM gap says the MLP barely moved from its zero-init residual baseline — first-epoch training peaked, and the DFL forecast remained close to DAM throughout. The EV gap says the MLP did not capture what the bootstrap scenario mean encodes: empirical inter-hour price corrections aggregated over **K=15 analog-day scenarios** with recency weighting. Both gaps are consistent with weak training signal (causes 1 and 2) more than with MLP capacity limitations.

### What the PoC establishes

1. End-to-end DFL training through a differentiable QP is implementable with cvxpylayers for BESS problems, provided the problem is in per-unit form and T is kept small.
2. The "train on short horizon, eval on long horizon" mismatch is a concrete, addressable failure mode for future work.
3. The DAM-baseline zero-init is a strong prior: the MLP already starts at 67.8% of PF, and DFL in this configuration neither beats nor significantly degrades that baseline (−0.8%).

### Out of scope (future work)

- Training with T=288 via ECOS or direct KKT: eliminates the horizon mismatch
- SPO+ loss instead of implicit differentiation: avoids SCS entirely
- Transformer architecture for longer-range temporal features
- Multi-panel evaluation and ablation studies
