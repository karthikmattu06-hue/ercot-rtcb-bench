# W3-C Backtest Results

| Method | Total | Energy | AS | Terminal liq. | vs PF |
|---|---|---|---|---|---|
| PF LP (upper bound) | $351,612 | $253,765 | $97,601 | $245 | 100.0% |
| Deterministic LP — DAM forecast | $238,421 | $185,034 | $47,871 | $5,516 | 67.8% |
| Deterministic LP — scenario mean (EV) | $250,174 | $168,703 | $73,412 | $8,058 | 71.2% |
| Stochastic LP — scenario tree | $238,376 | $159,021 | $72,478 | $6,878 | 67.8% |

**Panel:** Apr 20–26, 2026 (UTC). **BESS:** 100 MW / 400 MWh, RTE=0.88, HB_HUBAVG.
**Canonical seed:** 42. **Planning resolution:** 5-min native.

## In-Expectation VSS (formulation correctness check)

The in-expectation VSS measures what stochastic optimization adds over the EV solution
*within the scenario model* — isolated from forecaster quality. It is provably ≥ 0 for
a correct risk-neutral two-stage formulation.

`In-expectation VSS = Σ_h (RP_h − EEV_h) = $+9,967.3912` — **CONFIRMED ≥ 0 (formulation correct)**

Per-hour range: [-0.0000, 588.3995] (all hours non-negative)

RP_h = stochastic LP's optimal expected revenue at hour h (from Gurobi ObjVal).
EEV_h = EV solution's first-stage fixed, stage-2 optimized per scenario from the same state.
Both start from the stochastic LP's actual SoC at hour h; VSS_h ≥ 0 is guaranteed by LP
optimality (EV+recourse is a feasible point for the stochastic LP).

## Realized revenue gap (Stochastic − EV), out-of-sample

This is the settled-revenue difference on actual Apr 20–26 RT prices — **not** the
in-expectation VSS. It can be negative when the scenario distribution misrepresents reality.

Realized gap = $-11,797 (Stochastic $238,376 − EV $250,174)

Decomposition (settled revenue, Stochastic − EV):
- Energy: $-9,683
- AS: $-935
- Terminal liquidation: $-1,180

**Interpretation:** The stochastic LP makes recourse-aware first-stage decisions —
it holds more SoC flexibility because flexibility has expected value across the scenario
fan. On this panel, those decisions are more conservative than the EV plan and settle
for less energy revenue, because the actual Apr 20–26 realized above the scenario-mean
center (~−7 $/MWh biased). The negative realized gap is dominated by forecaster
misspecification (biased scenario center), not a deficiency of the stochastic formulation —
the non-negative in-expectation VSS confirms the optimization itself adds value given its
scenario model.

**Positive finding:** EV deterministic (scenario mean) beats DAM deterministic by
$+11,753 (+4.9%). The bootstrap-mean is a better bidding
input than DAM for this panel.

## Stochastic vs DAM-deterministic: three-bucket decomposition (confounded, reference only)

The Stochastic-vs-DAM gap conflates differently-centered forecasts (scenario mean ≠ DAM).
- Energy: $-26,013
- AS: $+24,607
- Terminal liquidation: $+1,362
- Net: $-44

Two effects: the ~−7 $/MWh scenario-mean bias makes energy look less attractive
relative to AS, driving a capacity reallocation (−$26k energy, +$25k AS). The recourse-
aware stochastic plan shifts further below EV (additional −$9.7k energy), reflecting
SoC flexibility preservation.

## Confirm-solve (Task 2)
- Hour: 2026-04-25 18:00:00+00:00
- K=15, T1=12, T2=276
- Variables (approx): 33,232
- Solve time: 0.182s

## Caveats

**AS-scoping caveat:** W3-B AS scenarios are under-dispersed (~51–56% 80% coverage),
so the stochastic LP treats AS near-deterministically. In-expectation VSS reflects
energy-side recourse value only.

**LMP-bias caveat:** Scenario mean carries ~−7 $/MWh directional bias (frozen panel
artifact). Both EV and stochastic share this bias; it cancels in the in-expectation VSS
but dominates the realized revenue gap.
