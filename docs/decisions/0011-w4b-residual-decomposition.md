# ADR 0011 — W4-B: Residual Decomposition (Formulation Gap + Dispersion Calibration)

**Status:** Accepted
**Date:** 2026-06-10

---

## Context

W4-A (ADR 0010) decomposed the **Stochastic→PF headroom of $113,236** into an LMP
mean-bias leg (ΔLMP = $21,479), an AS effective-price leg (ΔAS = $36,393), a small
interaction (−$2,194), and an unexplained **residual of $57,558** (50.8%). W4-B
decomposes that residual into:

- **G** — formulation/rolling-horizon gap (structural, not forecast-reducible)
- **ΔLMPdisp** — LMP dispersion calibration (lower bound)
- **ΔASdisp** — AS dispersion calibration (lower bound)
- **remainder** — beyond-calibration forecast misspecification + finite-K sampling

**Standing caveat:** dispersion oracles are *calibration oracles* — they fix only
the second moment, so each Δ·disp is a **lower bound** on the achievable gain.

**Out of scope:** no forecaster fixes, no K=50 re-run executed (only triggered/assessed).

---

## Decisions

### 1. Formulation probe — clamp at PANEL_END; G designated $14

The formulation gap is measured by R_struct: the stochastic LP run with **all K
scenarios set to the realized RT path** (perfect center, zero dispersion). G = PF −
R_struct.

**Boundary-convention artifact (finding-grade).** An unclamped 24h rolling window
extends past PANEL_END for the final panel hours, letting the perfect-foresight LP
position SoC for post-panel arbitrage and bank it as terminal liquidation (+$5,873
vs PF's $245). This made the unclamped R_struct = $353,017 *exceed* full-panel PF
($351,612) → G = −$1,405, which is impossible (PF must weakly dominate a myopic
rolling LP). The canonical probe **clamps each window at PANEL_END** so no
post-panel interval enters the objective; the final hour clamps to its committed
hour (T2=0 → zero terminal value → battery drains, matching PF). This required a
defensive guard in `stochastic_lp.py` (`terminal_lmp_k = mean(lmp2k) if lmp2k.size
else 0.0`), a no-op for all T2>0 callers. The clamp applies to the probe ONLY;
baseline/CF/Phase-2 runs keep the standard harness convention.

**G is bracketed [$14, $4,467] by boundary treatment; $14 is designated.**

- **$14** (designated) — clamped, total-revenue: PF − R_struct_clamped = $351,612 −
  $351,598. Unit-consistent with the $57,558 residual (total revenue incl.
  liquidation, same convention).
- **$4,467** — in-panel energy+AS only (unclamped). A *decomposition detail*: the
  rolling LP loses $924 of in-panel arbitrage timing vs PF but strands ~$911 more
  terminal SoC; the two nearly cancel in total revenue. This is **not** an
  alternative G.

**Finding — structural cost ≈ 0.** A 100 MW / 400 MWh (4-hour) battery's economic
value horizon fits inside the 24h lookahead, so a perfect-foresight two-stage
rolling LP recovers essentially all of full-panel PF. **The residual is essentially
all forecast-side.**

### 2. LMP dispersion oracle — global scale, calibration succeeds

A single global scale s applied on top of CF-A centering (mean-preserving around
the per-interval mean; no E[max]). Coverage is monotone in s; bisection to 80%
central coverage gives **s_lmp = 0.465** (q80: 0.950 → 0.801).

**Finding — LMP is OVER-dispersed post-centering.** This reverses the
under-dispersion assumption. W3-B reported ~87.7% LMP coverage (ADR 0007) on raw
scenarios carrying a −7.6 $/MWh bias; the bias displaced the prediction interval
while over-dispersion widened it, and the two offset to *look* calibrated. CF-A
removes the bias, exposing the over-dispersion (q80 0.95) → the oracle *narrows*
(s < 1).

### 3. AS dispersion oracle — best-achievable scale; family is ill-posed

Per-product scale s_p applied on top of the raw scenarios, then the E[max] δ is
**re-solved** per (p,h) to hold effective price = realized. **80% central coverage
is unreachable**: coverage is non-monotone in s_p and peaks below 0.80 for every
product (regup 0.79, regdn 0.67, nspin 0.58, rrs 0.52, ecrs 0.50).

**Mechanism (finding-grade).** E[max(price,0)] = realized + non-negative AS prices
means widening the raw spread forces δ sharply negative to hold the small positive
effective mean; the distribution bulk goes below zero and the central interval
slides *beneath* realized → coverage *falls* as you widen. CF-AB already sits within
~0.04 of each product's ceiling → **essentially no AS dispersion-calibration
headroom.** We therefore set each s_p to its **coverage-maximizing value**
(argmax: regup 1.15, regdn 0.70, rrs 0.45, ecrs 0.55, nspin 0.50); ΔASdisp is a
lower bound and the *finding is the sub-80% ceiling itself*.

**Implication:** the AS location-scale family is **representationally ill-posed**
under E[max] + non-negativity. v0.2 AS dispersion work requires a **scenario-family
change** (quantile mapping / copula / generative), not rescaling. This continues the
W4-A CF-B saga (clip → residual-centering → E[max]): AS non-negativity keeps
breaking moment-based calibration.

### 4. Perfect-path upper bounds (bracket)

Two standard-harness runs on top of CF-AB give per-leg perfect-foresight upper
bounds: **U_LMP** (realized LMP + E[max] AS) and **U_AS** (CF-A LMP + realized AS).
ΔLMP_upper = U_LMP − CF-AB, ΔAS_upper = U_AS − CF-AB. The cross-check **U_both
(realized both) ≡ unclamped R_struct = $353,016.61** (cent-exact) validates the
realized-path machinery. Perfect-path legs inherit the boundary-lookahead artifact
(≤ ~$1.4k); **method-vs-method comparisons are unaffected** — the artifact only
shifts method-vs-PF by the ≤$1.4k boundary scale.

---

## Consequences

### Residual decomposition ($57,558 = PF − CF-AB)

| Leg | Amount | Share | Bracket [cal, perfect-path] |
|---|---:|---:|---|
| ΔLMPdisp | +$5,866 | 10.2% | [$5,866, **$56,713**] |
| ΔASdisp | +$244 | 0.4% | [$244, $3,347] |
| Interaction | −$157 | −0.3% | — |
| **Remainder** | **+$51,605** | **89.7%** | — |
| **Total** | **$57,558** | **100.0%** | — |

Identity: $5,866 + $244 − $157 + $51,605 = **$57,558** ✓
Formulation gap G = **$14** (designated; bracket [$14, $4,467]).

### Interpretation

#### (1) The remainder is beyond-per-hour-mean LMP content + EVPI — not re-measured point error

The ΔLMP_upper bracket ($56,713) is **not** a point-forecast (mean) error: the
per-hour LMP mean bias was already removed in CF-AB (W4-A ΔLMP = $21,479) and is
**not double-counted** here. ΔLMP_upper measures the content *beyond* the per-hour
mean — **inter-scenario distributional realism, intra-hour 5-min price shape, and the
expected value of perfect information (EVPI)**. It is a **clairvoyant** bound
(realized path as every scenario) and therefore includes EVPI that **no forecaster
can capture**.

The **bankable** LMP dispersion gain is the calibration lower bound, **$5,866**. The
bracket interior [$5,866, $56,713] mixes reducible misspecification with irreducible
EVPI; the two are **not separately identified** here, so the **harvestable fraction
is unknown**. (PF − U_LMP = $844 is within the boundary-artifact scale ~$1.4k — noise,
not a measured gap.)

#### (2) Formulation structure is not the bottleneck

G ≈ $14 (≤ $4,467 under any boundary convention). The two-stage 24h rolling LP is
near-optimal for a 4-hour battery under perfect foresight. No formulation redesign
(longer horizon, more stages) is warranted by this panel.

#### (3) Formulation is tight; K=15 is not separately exonerated, but K=50 is still not warranted

U_both (K=15 scenarios, all = realized path) reaches $353,017 ≈ PF. This proves the
two-stage rolling **formulation is tight under degenerate (identical) scenarios** —
where K is irrelevant — **not** that K=15 suffices under genuine dispersion. The
**K-probe trigger fires mechanically** (remainder $51,605 > ~$17k); we **override it**
with stated rationale: the K-sensitive *measured* legs are small (ΔLMPdisp $5,866 +
ΔASdisp $244), and the remainder is dominated by beyond-calibration LMP content (§1)
where scenario count is second-order. **Recommend NOT running K=50** — the expected
payoff is bounded by the small dispersion legs, not the large remainder.

#### (4) AS is a minor lever and irreducible by rescaling

Perfect AS foresight recovers $3,347; AS dispersion calibration buys $244. The AS
family must change (§3) for any further AS gain.

### v0.2 work ordering by bankability (spans W4-A + W4-B levers; revises ADR 0010 §Interpretation(4))

Ranked by **bankable** revenue (clairvoyant / EVPI content excluded):

1. **AS effective-price correction — $36.4k** (W4-A ΔAS): the largest bankable
   lever; the E[max] effective-price error. **(Update, W5-A / ADR 0012:** partially
   banked at **50.2% recovery** — +$18,271 on the eval panel via scarcity-conditioned
   DAM-anchor shrinkage. The remaining ≈ $18.1k is **unattributed**; candidate
   contributors include the nspin anchor residual, AS distribution realism (item 4),
   and the panel variance evident in W5-A's loss days — none measured. One-week panel;
   second-panel replication required before the lever is claimed.**)**
2. **LMP evening-peak mean correction — $21.5k** (W4-A ΔLMP): concentrated in
   HoD 0–1; regime-aware analog selection / evening-peak recalibration.
3. **LMP spread narrowing — $5.9k** (W4-B ΔLMPdisp, s≈0.47): near-free; LMP
   scenarios are over-dispersed post-centering (§2 of Decisions) — simply narrow them.
4. **AS scenario-family change — [$0.2k, $3.3k]** (W4-B): quantile-mapping / copula
   / generative AS scenarios; rescaling cannot fix AS coverage (§3 of Decisions).
5. **LMP distribution realism / intra-hour shape — ≤$50.8k minus unknown EVPI**
   (W4-B remainder, §1): research-grade, harvestable fraction unknown — **not a v0.2
   commitment**.

**Not warranted:** K=50 re-run (override, §3); formulation redesign (G ≈ 0, §2).

### Cross-checks

- Identity = $57,557.64 (exact).
- remainder ($51,605) ≳ G ($14) ✓ — mixed-convention (remainder total-revenue vs G
  clamped), bounded by the ≤$1.4k boundary artifact.
- U_both ≡ unclamped R_struct (cent-exact), validating v2 machinery.

### Out of scope (future work)

- **AS generative scenarios:** replace location-scale rescaling with a family that
  can represent the AS coverage shape (§3).
- **Cross-panel validation:** all magnitudes are from a single 7-day panel with a
  specific evening-peak episode.
- **LMP point-forecast model:** the $56,713 perfect-path LMP potential is the v0.2
  forecaster target; method TBD (regime-aware analogs, longer lookback, learned).
