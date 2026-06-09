# ADR 0008: W3-C Two-Stage Stochastic LP Bidding Method

**Status:** Accepted
**Date:** 2026-05-16
**Author:** Karthik Mattu

---

## Context

W3-C implements causal (deployable) bidding methods for the Apr 20–26, 2026 panel
and compares them to the perfect-foresight LP upper bound from W3-B. The goals are:
1. Isolate the value of **rolling-horizon re-optimization**: re-solve each hour as
   new information arrives, using a 24h lookahead.
2. Isolate the **value of stochastic optimization**: stochastic LP over the W3-B
   ScenarioTree vs. a point-forecast deterministic LP.

W3-A (Task 0 audit) found that the existing "deterministic MILP" was a single-window
LP, not rolling-horizon. Decision: build rolling-horizon wrappers for the two causal
methods; keep PF single-window; correct all bidding-method terminology from MILP to LP
(no binary variables appear in any of these formulations; "MILP" was a misnomer).

---

## Decision

### Architecture: Rolling-horizon LP

**Causal methods** use a 24h rolling-horizon LP:
- Re-solve every hour; commit only the first 12 intervals (T1 = 12, one 5-min hour).
- 24h lookahead: T1 = 12 (stage 1, committed) + T2 = 276 (stage 2, recourse).
- **Terminal value function:** `SoC_end × mean(LMP_lookahead)`. Internal optimization
  device that prevents the LP from depleting SoC at the planning horizon. NOT included
  in reported revenue — convention is end-of-window liquidation at final RT LMP.
- SoC carry-forward uses the audited physical formula:
  `s_{t+1} = s_t − dt·d_t + dt·rte·c_t` (not the LP's internal SoC tracking).

**Perfect-foresight LP** (PF): single full-window LP over the entire 7-day panel.
Kept single-window because a rolling PF would conflate the information advantage
(full future visibility) with the structural change (rolling vs. single-window).

**End-of-window liquidation**: at panel end, remaining SoC is liquidated at the final
5-min RT LMP and added to all methods' revenue identically. Reported as a separate bucket.

### Stochastic LP extension

Each hour's stochastic LP is a two-stage program:
- Stage 1 (T1 = 12): scenario-independent decisions — non-anticipativity by
  construction (one set of d, c, AS awards for all scenarios).
- Stage 2 (T2 = 276, K scenarios): per-scenario recourse.
- Objective: `Σ_k p_k × [stage1_revenue + stage2_revenue_k + terminal_k]`

Stage-1 prices: probability-weighted scenario mean (`Σ_k p_k · stage1_scenario_k`).
Stage-2 scenarios: K = 15 scenario fan from the W3-B ScenarioTree.
Terminal value per scenario: `p_k × mean(LMP_stage2_k) × SoC_end_k`.

Implementation: gurobipy MVar vectorized constraints — 33,232 variables,
~16,624 constraints per solve. Solve time: ~0.12s/hr, 168-hour panel: ~21s total.

### EV comparator (W3-C-rev-2 addition)

The original W3-C-rev gate compared Deterministic-LP-on-DAM vs Stochastic-LP-on-
scenarios — two methods using differently-centered forecasts. The W3-B LMP scenarios
carry a ~−7 $/MWh bias relative to DAM (frozen panel artifact); this difference
confounds the comparison and is the dominant driver of any revenue gap.

The standard tool for isolating distributional value is the **Value of the Stochastic
Solution (VSS)**. Two quantities are tracked:

**In-expectation VSS** (formulation check): `VSS = Σ_h (RP_h − EEV_h)` where:
- RP_h = stochastic LP's optimal expected revenue at hour h (Gurobi ObjVal).
- EEV_h = EV-deterministic LP's first-stage decision fixed, stage-2 optimized
  per scenario, probability-weighted — both from the same initial state as RP_h.
- VSS_h ≥ 0 is provably guaranteed for a correct risk-neutral two-stage LP.

**Realized revenue gap**: `(stochastic settled revenue) − (EV settled revenue)`,
evaluated against actual Apr 20–26 RT prices. This can be negative when the scenario
distribution misrepresents reality.

The Deterministic-LP-on-DAM run is retained as the "competent operator" baseline
(DAM prices are what a real operator has), not as the stochastic LP comparator.

---

## Results: Apr 20–26, 2026 Panel

BESS: 100 MW / 400 MWh, RTE = 0.88, HB_HUBAVG. Canonical seed: 42.

| Method | Total | Energy | AS | Terminal liq. | vs PF |
|---|---|---|---|---|---|
| PF LP (upper bound) | $351,612 | $253,765 | $97,601 | $245 | 100.0% |
| Deterministic LP — DAM forecast | $238,421 | $185,034 | $47,871 | $5,516 | 67.8% |
| Deterministic LP — scenario mean (EV) | $250,174 | $168,703 | $73,412 | $8,058 | 71.2% |
| Stochastic LP — scenario tree | $238,376 | $159,021 | $72,478 | $6,878 | 67.8% |

### In-expectation VSS (formulation confirmation)

`Aggregate in-expectation VSS = $+9,967` (sum over 168 rolling hours)

Per-hour range: [$0.000, $588.40]. All 168 hours non-negative (floating-point noise
on near-zero hours < 1e-9, well within the 10-cent formulation-bug threshold).

**The stochastic LP formulation is correct.** The positive in-expectation VSS confirms
that modeling the scenario distribution adds expected value over fixing to the EV
decision, given the scenario model. The magnitude (~$60/hr mean) reflects the value of
SoC flexibility preserved by the recourse-aware stage-1 decisions.

### Realized revenue gap (out-of-sample)

`Realized gap = $238,376 − $250,174 = −$11,797` (Stochastic − EV)

Decomposition (settled revenue, Stochastic − EV):
- Energy: −$9,682
- AS: −$934
- Terminal liquidation: −$1,180

This gap is **dominated by forecaster misspecification**, not a deficiency of the
stochastic formulation. The scenario fan is centered ~−7 $/MWh on energy. The
stochastic LP's recourse-aware stage-1 makes SoC-preserving decisions (flexibility
has expected value across the scenario fan). When actual Apr 20–26 prices realized
above the scenario center, those recourse-aware positions settled for less energy
revenue. The non-negative in-expectation VSS shows the optimization adds value
*given its scenario model*; the model's bias is the W3-B forecaster's limitation.

**Interpretation note:** The stochastic LP is risk-neutral. It does not "hedge"
against low-price scenarios in a risk-averse sense. It makes **recourse-aware**
first-stage decisions — preserving SoC flexibility because flexibility has expected
value across the fan. The consequence of this on settled revenue depends on whether
actual realized prices are above or below the scenario center.

### Positive finding: EV beats DAM as a bidding input

`EV − DAM = $250,174 − $238,421 = +$11,753 (+4.9% of DAM revenue)`

The bootstrap-mean scenario forecast is a better bidding input than DAM prices on this
panel. EV captures 71.2% of PF vs. DAM's 67.8% — a clear separation. The scenario
mean shifts the optimizer toward more AS (matching the RT market's actual AS premium)
and earns higher settled revenue.

### Stochastic-vs-DAM decomposition (confounded, reference only)

The W3-C-rev original Stochastic-vs-DAM gap (−$44 total) has a single root cause:
the ~−7 $/MWh scenario-mean bias makes energy look less attractive relative to AS,
driving a capacity reallocation. Decomposed: energy −$26k, AS +$25k, liq +$1.4k.
The stochastic LP's further energy conservatism vs. EV (−$9.7k) reflects recourse-
aware SoC preservation — a separate, coherent effect on top of the bias-driven shift.

---

## Carry-forward Caveats

**AS-scoping caveat**: W3-B AS scenarios are under-dispersed (~51–56% 80% coverage);
AS EV ≈ stochastic AS ($73.4k vs $72.5k) confirms no meaningful AS-side recourse
value in v0.1. In-expectation VSS is effectively an energy-side measure.

**LMP-bias caveat**: Scenario mean carries ~−7 $/MWh directional bias (frozen
Apr 20–26 panel artifact — winter-dominated analog pool). Both EV and stochastic
share this bias; it cancels in in-expectation VSS, but dominates the realized
revenue gap and both methods' absolute energy revenue vs. PF and vs. DAM.

---

## Rejected Alternatives

**Single-window stochastic LP**: Causal methods must re-solve as new information
arrives. Single-window stochastic has access to future scenario structure not
available at decision time, conflating informational advantage with method structure.

**CVaR risk objective**: Deferred to v0.2. v0.1 is a risk-neutral baseline;
introducing CVaR without principled calibration would constitute tuning.

**Binary variables**: No binary variables appear in any bidding formulation.
Simultaneous charge+discharge is LP-suboptimal and doesn't need integer enforcement.
"MILP" in pre-W3-C references was a misnomer; all bidding methods are pure LPs.

---

## Consequences

- **W3-D (DFL)** receives the characterized LP baselines. PF LP is the imitation-
  learning target. DAM-deterministic (67.8% capture) is the operator-floor baseline.
  EV (71.2%) shows the forecast-center improvement available without distributional
  modeling; the remaining gap to PF motivates DFL and DRL.
- **In-expectation VSS as energy-side measure**: v0.1 VSS ($+9,967 aggregate) is
  interpretable only as energy-side recourse value given near-deterministic AS. Report
  it as such.
- **Realized revenue gap as joint metric**: the −$11,797 realized gap is a joint
  (method × v0.1-forecaster) outcome — not a standalone verdict on stochastic optimization.
- **Terminology**: All bidding method references use "LP." ERCOT's SCED MIP and its
  optimality gap are unaffected — those are distinct from the benchmark methods.
- **Reproducibility**: Canonical seed 42. Re-run `scripts/backtest_w3c.py` to reproduce
  all four revenue rows and the in-expectation VSS.
