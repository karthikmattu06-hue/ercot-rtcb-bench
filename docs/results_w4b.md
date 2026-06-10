# W4-B Results: Residual Decomposition (Formulation Gap + Dispersion Calibration)

**Panel:** Apr 20–26, 2026 (168 hours)
**BESS:** 100 MW / 400 MWh, RTE=0.88
**Solver:** Gurobi (license renewed)
**Canonical seed:** 42 (per-day independent RNG, ADR 0007)

Decomposes the **$57,558 CF-AB→PF residual** left after W4-A's effective-price
oracles — the unexplained 50.8% of the Stochastic→PF headroom.

---

## Phase 0 — Formulation probe (HARD GATE)

| Quantity | Value |
|---|---:|
| CF-AB reproduced | $294,054.36 (drift −$0.00) |
| R_struct **unclamped** (24h window peeks past panel) | $353,016.61 |
| R_struct **clamped** at PANEL_END (canonical) | $351,597.92 |
| **G_canonical = PF − R_struct_clamped** | **+$14.08** |
| G_inpanel cross-check (energy+AS only, unclamped) | +$4,467.31 |

**Boundary-convention artifact.** An unclamped 24h rolling window lets the
perfect-foresight LP bank post-panel SoC as terminal liquidation (+$5,873 vs PF's
$245), making R_struct *exceed* full-panel PF (G = −$1,405, impossible). Clamping
each window at PANEL_END removes the leak and restores PF ≥ rolling.

**Finding — formulation gap ≈ 0.** A 100 MW / 400 MWh (4-hour) battery's economic
value horizon fits inside the 24h lookahead, so a perfect-foresight two-stage
rolling LP recovers essentially all of full-panel PF. **G is bracketed
[$14, $4,467] by boundary treatment; $14 is designated** (total-revenue,
unit-consistent with the $57,558 residual). The in-panel $4,467 is a decomposition
detail (in-panel timing loss offset by terminal SoC stranding), not an alternative
G. **The residual is essentially all forecast-side, not structural.**

---

## Phase 1 — Dispersion calibration oracles (on top of CF-AB)

Mean-preserving scale around the per-interval probability-weighted mean:
`s_k(t) → m(t) + scale·(s_k(t) − m(t))`. Preserves every per-interval mean (hence
CF-A's centering). Coverage = fraction of realized inside the central-80% scenario
interval, pooled panel-wide.

### 1.1 LMP — over-dispersed (calibration succeeds)

| | q50 | q80 | q90 |
|---|---:|---:|---:|
| Baseline (scale=1) | 0.769 | **0.950** | 0.973 |
| Calibrated (s_lmp = **0.465**) | 0.490 | **0.801** ✅ | 0.896 |

LMP scenarios are **over-dispersed** after CF-A centering — the opposite of the
under-dispersion assumption. W3-B reported ~87.7% LMP coverage (ADR 0007) on raw
scenarios carrying a −7.6 $/MWh bias; the bias displaced the interval while
over-dispersion widened it, and the two offset to *look* roughly calibrated.
Removing the bias (CF-A) exposes the over-dispersion (q80 0.95) → narrow to
s=0.465 for 80%.

### 1.2 AS — coverage ceiling below target (oracle ill-posed)

80% central coverage is **unreachable** under E[max] + non-negativity. Best-achievable
(argmax-coverage) scales and their ceilings:

| Product | base q80 | s_p* | **ceiling q80** |
|---|---:|---:|---:|
| regup | 0.784 | 1.15 | **0.790** |
| regdn | 0.666 | 0.70 | **0.668** |
| rrs | 0.475 | 0.45 | **0.515** |
| ecrs | 0.491 | 0.55 | **0.501** |
| nspin | 0.538 | 0.50 | **0.578** |

**Mechanism:** the E[max(price,0)] = realized constraint (CF-B) plus non-negative
AS prices means widening the raw spread forces δ sharply negative to hold the small
positive effective mean; that pushes the distribution bulk below zero, sliding the
central interval *beneath* realized → coverage *falls* as you widen. Coverage is
non-monotone in scale and peaks below 0.80 for every product. **CF-AB already sits
within ~0.04 of each ceiling → essentially no AS dispersion-calibration headroom.**

### 1.3 Verification gate

LMP at 0.801 (|err| 0.001 ≤ 0.03) **PASS**. AS ceilings recorded (0.80 proven
unreachable — informational). E[max] verification: 29 cells, max error 0.00099
$/MWh. **GATE 1.3 PASSED.**

---

## Phase 2 — Calibrated 2×2 + perfect-path bracket

All runs use the standard (unclamped) harness, directly comparable to CF-AB.

| Run | Revenue | Δ vs CF-AB |
|---|---:|---:|
| CF-AB baseline | $294,054.36 | — |
| +LMPdisp (s=0.465) | $299,920.81 | **+$5,866.45** |
| +ASdisp (s_p*) | $294,298.29 | **+$243.93** |
| +Both | $300,007.33 | (interaction −$157.41) |
| PF | $351,612.00 | (remainder +$51,604.67) |

### Residual decomposition ($57,558)

| Leg | Amount | Share |
|---|---:|---:|
| ΔLMPdisp (calibration) | +$5,866 | 10.2% |
| ΔASdisp (calibration) | +$244 | 0.4% |
| Interaction | −$157 | −0.3% |
| **Remainder** | **+$51,605** | **89.7%** |
| **Total** | **$57,558** | **100.0%** |

Identity check: $5,866 + $244 − $157 + $51,605 = **$57,558** ✓

### Bracket [calibration lower bound, perfect-path upper bound]

| Leg | Calibration (lower) | Perfect-path (upper) |
|---|---:|---:|
| LMP | +$5,866 | **+$56,713** |
| AS | +$244 | +$3,347 |

Perfect-path runs: U_LMP (realized LMP) = $350,768; U_AS (realized AS) = $297,401;
**U_both = $353,016.61 ≡ unclamped R_struct** (Phase-0 cross-check, cent-exact —
validates the v2 realized-path machinery). Perfect-path legs inherit the
boundary-lookahead artifact (≤ ~$1.4k); method-vs-method comparisons are unaffected.

---

## Interpretation

### The remainder is beyond-per-hour-mean LMP content + EVPI — not re-measured point error

The ΔLMP_upper bracket ($56,713) is **not** a point-forecast (mean) error — the
per-hour LMP mean bias was already removed in CF-AB (W4-A ΔLMP = $21,479; no
double-count). It measures content *beyond* the per-hour mean: inter-scenario
distributional realism, intra-hour 5-min price shape, and the expected value of
perfect information (EVPI). It is a **clairvoyant** bound and includes EVPI that **no
forecaster can capture**. The **bankable** LMP dispersion gain is the lower bound,
**$5,866**; the bracket interior [$5,866, $56,713] mixes reducible misspecification
with irreducible EVPI — not separately identified, harvestable fraction unknown.
(PF − U_LMP = $844 is within the boundary-artifact scale ~$1.4k — noise, not a
measured gap.)

### AS is a minor lever, and its dispersion is irreducible by rescaling

Perfect AS foresight recovers only $3,347. AS dispersion calibration buys $244.
The AS location-scale family is **representationally ill-posed** under E[max] +
non-negativity (coverage ceiling < 0.80 for all products) — v0.2 AS dispersion work
requires a **scenario-family change** (quantile mapping / copula / generative), not
rescaling.

### Formulation is tight; K=50 still not warranted

U_both (K=15 scenarios, all = realized path) reaches $353,017 ≈ PF. This proves the
two-stage rolling **formulation is tight under degenerate (identical) scenarios** —
where K is irrelevant — **not** that K=15 suffices under genuine dispersion. The
**K-probe trigger fires mechanically** (remainder $51,605 > ~$17k); it is **overridden**:
the K-sensitive measured legs are small (ΔLMPdisp $5,866 + ΔASdisp $244) and the
remainder is dominated by beyond-calibration LMP content (above), where scenario count
is second-order. **Recommend NOT running K=50** — the expected payoff is bounded by the
small dispersion legs, not the large remainder.

### Cross-checks

- Identity = $57,557.64 (exact).
- remainder ($51,605) ≳ G ($14) ✓ (mixed-convention, bounded by the ≤$1.4k
  boundary artifact).
- U_both ≡ unclamped R_struct, cent-exact.

---

## v0.2 work ordering by bankability (spans W4-A + W4-B; revises ADR 0010)

Ranked by **bankable** revenue (clairvoyant / EVPI content excluded):

1. **AS effective-price correction — $36.4k** (W4-A ΔAS): largest bankable lever.
2. **LMP evening-peak mean correction — $21.5k** (W4-A ΔLMP): HoD 0–1; regime-aware
   analog selection / evening-peak recalibration.
3. **LMP spread narrowing — $5.9k** (W4-B ΔLMPdisp, s≈0.47): near-free; LMP is
   over-dispersed post-centering — simply narrow.
4. **AS scenario-family change — [$0.2k, $3.3k]** (W4-B): quantile-mapping / copula /
   generative AS scenarios; rescaling cannot fix AS coverage.
5. **LMP distribution realism / intra-hour shape — ≤$50.8k minus unknown EVPI**
   (W4-B remainder): research-grade, harvestable fraction unknown — **not a v0.2
   commitment**.

**Not warranted:** K=50 re-run (override); formulation redesign (G ≈ 0).

---

## Engineering Notes

- **Formulation probe clamp** applies to the Phase-0 probe ONLY; baseline/CF/Phase-2
  runs keep the standard harness convention for comparability with W4-A. Required a
  defensive guard in `stochastic_lp.py`: `terminal_lmp_k = mean(lmp2k) if lmp2k.size
  else 0.0` (no-op for all T2>0 callers).
- **CF-AB reproduction:** exact through both the W4-A oracle path and the W4-B v2
  dispersion machinery (drift −$0.00 each).
- **Coverage:** weighted central-interval (Hazen plotting positions), pooled over
  Apr 20–26, near_zero AS cells excluded.
- **Runtime:** Phase 1 ~10s (numpy); Phase 2 ~431s (7 rolling LP runs, Gurobi).
