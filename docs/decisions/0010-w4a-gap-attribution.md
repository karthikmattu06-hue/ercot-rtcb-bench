# ADR 0010 — W4-A: Stochastic-LP→PF Gap Attribution (LMP Bias vs AS Effective-Price Error)

**Status:** Accepted  
**Date:** 2026-06-09

---

## Context

W3-C established on the Apr 20–26 panel:

| Method | Revenue | vs PF |
|---|---:|---:|
| PF LP (upper bound) | $351,612 | 100% |
| Stochastic LP (baseline) | $238,376 | 67.8% |
| EV-det LP | $250,174 | 71.2% |

The **Stochastic→PF headroom of $113,236** is the quantity this chunk decomposes. It covers two identifiable forecaster-error sources (LMP mean bias, AS effective-price error) and an unexplained residual.

**Out of scope:** The −$11,797 Stochastic-vs-EV-det realized gap is a W3-C observation that is NOT decomposed here; explaining it would require oracle runs on the EV-det LP as well. It is a candidate v0.2 follow-up.

---

## Decisions

### 1. Oracle CF-A — LMP mean centering

For each of the 168 operating hours h, shift each scenario's LMP values across the full 288-interval day-array by:

```
δ_lmp(h) = mean(RT_LMP, h_intervals) − weighted_mean_k(scenario_k_LMP, h_intervals)
```

Additive shift, no data-layer clip. LMP can be negative (both forecast and realized); no non-negativity issue. AS scenarios unchanged.

### 2. Oracle CF-B — AS E[max] retargeting

**Design progression (finding-grade — three approaches evaluated):**

**(i) Additive shift + clip ≥ 0** — rejected. The diagnostic showed the bootstrap scenarios *over-estimate* realized AS prices (FC mean > RT mean for all 5 products on this panel). CF-B therefore applies predominantly downward shifts. When scenarios are shifted down and clipped at 0, the effective scenario mean remains systematically above realized (clip error +$0.17–$0.59/MWh on average; up to +$3.64/MWh in hours where realized ≈ $0 and FC ≈ $10–16). ΔAS measured under (i) is a mixture of partial mean correction and clip-induced redistribution — not a clean leg.

**(ii) Residual-centering, no data-layer clip** — rejected. The stage-2 AS structure (T2=276 intervals, 95.8% of horizon) uses per-scenario recourse awards with lb=0.0. The LP effectively plans on E[max(price,0)] per scenario, not E[price]. With awards ≥ 0, any negative scenario prices are zeroed at the optimizer level. Residual-centering merely relocates the clip from the data layer to the optimizer's non-negativity constraint; the LP's effective planning quantity is unchanged. Raw mean-centering is therefore ill-posed for stage-2 AS.

**(iii) E[max] retargeting — adopted.** For each AS product p and operating hour h, find δ(p,h) via bisection such that:

```
mean_t( E_k[ max(scenario_k(p,t) + δ, 0) ] ) = realized_mean(RT_MCPC_p, h)
```

No data-layer clip. The max(·,0) lives inside the target expression, matching the quantity the stage-2 LP actually optimizes on. The function is monotone non-decreasing in δ, guaranteeing a unique root whenever the target is achievable. **Rationale:** realized RT MCPC ≥ 0, so realized_mean = realized E[max(·,0)]; this oracle sets the LP's *effective* AS price perception equal to realized.

**Edge cases (log counts):**
- `realized_mean < $0.01`: no finite root exists; scenarios for that (p,h) cell set to 0 directly. Logged: **66 cells (6.9%)**.
- `|δ| > $500/MWh` cap: **0 cells**.
- Non-convergence: **0 cells**.

**Bisection tolerance:** $0.001/MWh. Verification on 30 sampled (p,h) cells: max error 0.010/MWh (boundary near-zero cases at threshold), all other cells ≤ 0.001. PASSED.

**Stage-1 caveat (4.2% of horizon):** Stage 1 (T1=12 intervals, 1 committed hour) prices AS on the probability-weighted mean of the shifted scenarios, not on E[max(·,0)]. The E[max] oracle implies a small raw-mean undershoot for stage-1 AS pricing. This is bounded by the 4.2% share of the rolling horizon and is not engineered around.

### 3. Oracle CF-AB

Both CF-A (LMP centering) + CF-B (AS E[max] retargeting) applied simultaneously to the same scenario arrays. Used to compute the interaction term.

### 4. Baseline and CF-A frozen

Baseline ($238,376.27) and CF-A ($259,855.23) are reused from prior runs. CF-B and CF-AB re-run with the E[max] oracle.

---

## Consequences

### Phase 1 — Per-HoD LMP bias

| HoD (UTC) | Forecast | Realized | Bias |
|---:|---:|---:|---:|
| 0 | $83.57 | $132.34 | **−$48.77** |
| 1 | $79.46 | $126.71 | **−$47.25** |
| 2 | $85.96 | $67.03 | +$18.93 |
| 3 | $57.03 | $51.88 | +$5.15 |
| 4 | $27.42 | $28.27 | −$0.85 |
| 5 | $20.99 | $27.14 | −$6.15 |
| 6 | $23.66 | $25.34 | −$1.69 |
| 7 | $21.17 | $25.15 | −$3.98 |
| 8 | $22.77 | $26.08 | −$3.31 |
| 9 | $24.31 | $29.03 | −$4.72 |
| 10 | $33.26 | $33.78 | −$0.53 |
| 11 | $31.47 | $35.21 | −$3.74 |
| 12 | $30.91 | $32.33 | −$1.42 |
| 13 | $32.86 | $43.44 | −$10.59 |
| 14 | $20.56 | $31.13 | −$10.57 |
| 15 | $22.28 | $28.78 | −$6.50 |
| 16 | $16.86 | $26.24 | −$9.38 |
| 17 | $20.07 | $23.91 | −$3.84 |
| 18 | $22.44 | $27.09 | −$4.65 |
| 19 | $22.85 | $31.32 | −$8.47 |
| 20 | $30.95 | $34.23 | −$3.28 |
| 21 | $31.19 | $36.56 | −$5.37 |
| 22 | $35.75 | $34.79 | +$0.96 |
| 23 | $57.73 | $60.66 | −$2.93 |

**Verdict: peak-concentrated, not uniform.** HoD 0 and 1 UTC (7–8 pm CDT, the evening energy peak) dominate with −$48.77 and −$47.25/MWh. All other hours are mild (−$0.5 to −$10.6/MWh), with slight positive bias at HoD 2–3. Overall panel mean: −$6.79/MWh.

ΔLMP ($21,479) rides on roughly **14 operating hours** (2 HoDs × 7 days). The implied v0.2 fix is a targeted evening-peak correction — not a broad forecast recalibration. **Panel-sensitivity caveat:** this lever is concentrated on a one-week panel; its magnitude may not generalise to panels without an evening-peak underestimation episode.

### Phase 2 — Stochastic→PF attribution table

| Variant | Revenue | vs Baseline | vs PF |
|---|---:|---:|---:|
| Baseline (Stochastic LP) | $238,376 | — | −$113,236 |
| CF-A: Oracle LMP | $259,855 | +$21,479 | −$91,757 |
| CF-B: E[max] AS oracle | $274,770 | +$36,393 | −$76,842 |
| CF-AB: Oracle LMP + E[max] AS | $294,054 | +$55,678 | −$57,558 |
| PF LP (upper bound) | $351,612 | +$113,236 | — |

**Decomposition of the $113,236 Stochastic→PF headroom:**

| Leg | Amount | Share |
|---|---:|---:|
| ΔLMP (LMP mean bias) | +$21,479 | 19.0% |
| ΔAS (AS effective-price error) | +$36,393 | 32.1% |
| Interaction | −$2,194 | −1.9% |
| **Residual** | **+$57,558** | **50.8%** |
| **Total** | **$113,236** | **100.0%** |

Identity check: $21,479 + $36,393 − $2,194 + $57,558 = **$113,236** ✓

### Interpretation

#### (1) AS effective-price error is the larger identified forecaster lever

ΔAS ($36,393, 32.1%) is 1.69× ΔLMP ($21,479, 19.0%). **This refutes the hand-off hypothesis that LMP bias dominates.** However, the hedge is material: ΔAS measures the *effective-price* error only (the E[max(price,0)] planning quantity). AS *dispersion* — quantified in W3-B as 51–56% interval coverage vs an 80% target — is separately unmeasured and deferred to W4-B. AS dispersion could be a larger or smaller lever than the effective-price error; the ordering of AS vs LMP may change once dispersion is addressed.

#### (2) Together the two identified legs explain only 49.2% of the headroom

The combined correction (CF-AB, +$55,678) closes roughly half the Stochastic→PF gap. The residual of $57,558 (50.8%) is **not** attributable to a single source in this chunk. Its components — LMP scenario dispersion, AS dispersion, K=15 finite-scenario sampling error, LP formulation gap (two-stage vs multi-stage), and irreducible uncertainty — are not separately identified here. PF is an unattainable ceiling (it uses future RT prices directly), so the majority of the residual is reducible-in-principle and constitutes the W4-B/v0.2 work surface.

#### (3) Interaction is small: approximately additive with mild diminishing returns

Interaction = −$2,194 (−1.9% of headroom, −3.9% of combined main effects $55,872). The two corrections address largely distinct LP decision margins — energy dispatch for LMP, AS commitment for AS — and their joint effect is close to the sum of individual effects. The slight negative interaction (diminishing returns) is consistent with shared capacity constraints binding tighter when both oracles are active simultaneously.

#### (4) v0.2 work ordering

The 50.8% residual is the largest unattributed bucket and should be measured before acting on the identified levers. Recommended ordering:

1. **W4-B dispersion oracle (highest priority):** run an AS dispersion oracle (scale scenarios to 80% interval coverage) and an LMP dispersion probe. AS dispersion could dominate the effective-price correction already measured; the ordering of AS vs LMP levers is not stable until this is quantified.
2. **AS effective-price correction (32.1%, largest measured lever):** once dispersion is sized, the combined AS oracle (effective-price + dispersion) gives the full AS improvement potential and informs whether an analog-day selector improvement is the right intervention.
3. **Targeted LMP evening-peak correction (19.0%, concentrated, panel-sensitive):** the bias is concentrated in ~14 of 168 operating hours (HoD 0–1 UTC, 7–8 pm CDT). A targeted fix — regime-aware analog selection or a post-processing recalibration for evening-peak hours — is the right scope. A broad forecast recalibration is not warranted by this data.

#### (5) The E[max] oracle design itself is a contribution

Naive mean-centering (additive shift + clip) is ill-posed for stochastic LPs with per-scenario non-negative recourse awards: the clip is merely relocated from the data layer to the optimizer. The E[max] retargeting oracle — correcting the LP's *actual* planning quantity — is the correct formulation for stage-2 AS attribution in this two-stage LP structure. The design progression (clip rejected → residual-centering rejected → E[max] adopted) is recorded as finding-grade detail in Decision §2.

### Out of scope (future work)

- **AS dispersion oracle (W4-B):** Scale scenario dispersion so the prediction interval covers realized AS prices at ~80%. This is the second leg of the W3-B AS under-coverage finding; ΔAS above measures only the effective-price (mean) error.
- **Cross-panel validation:** Attribution magnitudes are from a single 7-day panel with a specific evening-peak underestimation episode. Replication across multiple evaluation windows is needed before v0.2 roadmap decisions.
- **Stochastic-vs-EV-det gap decomposition:** The −$11,797 realized gap between Stochastic LP and EV-det LP requires oracle runs on both arms and is out of scope for this chunk.
- **Analog-day selector improvement:** The HoD 0–1 bias suggests bootstrap analogs lack historical days with similar evening-peak intensity. A price-regime–aware selector or a longer lookback with regime conditioning could reduce this lever.
