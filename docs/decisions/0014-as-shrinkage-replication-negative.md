# ADR 0014 — AS anchor shrinkage fails out-of-sample replication (W5-R)

**Status:** Accepted (negative result)
**Date:** 2026-06-14

---

## Context

ADR 0012 made second-panel replication a precondition for claiming the AS anchor
shrinkage lever (W5-A eval: +$18,271, 50.2% of the $36,393 oracle bound — a *single*
panel whose gain was driven by one scarcity day with two loss days). W5-R pulled the
data to unblock it (ADR 0013, baseline re-pinned to the canonical-faithful build
$238,378.80), then ran the **frozen** (τ_p, s_p) — asserted identical to ADR 0012, no
refit — on three new pre-registered panels (two scarcity, one calm), with the selection
metric (τ_p qualifying counts) and interpretation fixed in advance.

**This ADR keeps the diagnostic and the fix strictly separable: the diagnostic
survives; the fix is retired.**

## Results (cross-panel)

| Panel | Δ | Δ / PF-headroom | worst day | E & AS both up |
|---|---:|---:|---:|:--:|
| Apr 20–26 (eval, restated $238,378.80 base) | +$18,270 | 16.2% | −$5,524 | yes |
| Jun 1–7 (scarcity, primary, most-scarce) | −$4,765 | −4.6% | −$8,755 | no |
| May 4–10 (calm) | −$10,619 | −18.8% | −$7,514 | no |
| Apr 27–May 3 (scarcity, confirmatory) | +$6,303 | 6.8% | −$15,025 | yes |

The eval panel reproduces W5-A on the re-pinned baseline (+$18,270 ≈ +$18,271),
confirming the ADR 0013 shift was cosmetic.

## Findings (the contribution)

1. **Does not replicate.** Two of three new panels lose, and the **most-scarce week
   (Jun 1–7) loses** — the strongest refutation, since that is precisely where a
   real AS-over-forecast correction should win most.
2. **Mechanism — the "symmetric risk" is the dominant effect out-of-sample.** The lever
   is a directional bet that DAM over-forecasts AS. On Δ>0 panels (eval, Apr 27–May 3)
   energy *and* AS both rise (the reallocation mechanism of ADR 0012). On Δ<0 panels
   (Jun 1–7, May 4–10) energy *and* AS both **fall**: the frozen shrink **under-commits
   AS in weeks where the scarcity actually realizes in RT**. The "symmetric risk" hedge
   noted in ADR 0012 was not a tail caveat — it was the dominant behavior.
3. **One-day-driven is a property of the intervention, not an Apr-25 quirk.** Every
   panel's net is the residual of ±$5–19k single-day swings (eval +$18.7k on Apr 25;
   Apr 27–May 3 a −$15.0k/+$18.9k Apr 27/28 swing; Jun 4 −$8.8k; May 5 −$7.5k). W5-A's
   favorable-day dependence is universal here.
4. **Calm downside unbounded vs the precedent.** May 4–10 loses $10,619 (−18.8% of
   headroom), worst day −$7,514 — *larger* than the −$5,524 the single W5-A panel
   suggested as the worst case.

## Decision

- **Retire the frozen, unconditional AS anchor shrinkage as a revenue lever.** It is
  not v0.2/preprint-claimable as an improvement.
- **Retain the W5-A Phase-1 diagnostic in full** (`docs/results_w5a_diagnostic.md`):
  AS is systematically over-forecast, scarcity-concentrated, originating in the DAM
  anchor; RegDn flat. This is a *measurement* and is unaffected by the fix's failure.
- **Keep `ASAnchorCorrection` in the codebase behind its flag (default OFF)** as the
  artifact this negative result refers to. Do not delete it.
- **Lesson (recorded):** a static, unconditional correction cannot bankably capture a
  *state-dependent* error whose realization is itself uncertain. Capturing the AS bound
  would require conditioning on whether scarcity *realizes* — a forecasting,
  EVPI-adjacent problem — which connects to the W4-B finding that the residual is partly
  beyond-calibration content an unconditional fix cannot reach.

## v0.2 work ordering (forward note; supersedes the ADR 0011/0012 ordering)

Consistent with the ADR 0013 forward-only precedent, this updates the ordering without
editing the ADR 0011/0012 bodies:

- **AS effective-price lever — bound measured ($36.4k), correction built, retired on
  replication. NOT banked.** The diagnostic stands; the fix does not.
- **Next: W5-B — LMP evening-peak mean correction (~$21.5k, W4-A ΔLMP)** — but see the
  open thread: it is structurally the *same shape* (a concentrated mean bias) that just
  failed for AS, so it must be replication-native and bias-stability-prechecked.
- LMP spread narrowing ($5.9k), AS scenario-family change, LMP distribution realism —
  unchanged from ADR 0011, behind W5-B.

## Open threads

- **W5-B precheck (NEW, queued):** before building any LMP evening-peak fix, run a
  cross-panel bias-stability diagnostic on the six eligible weeks — is the evening-peak
  LMP bias directionally stable week-to-week, or does it flip sign like the AS payoff
  did? If unstable, a static fix is dead on arrival. Replication must be built into the
  W5-B eval from the first run, not retrofitted.
- **nspin anchor over-quote** (ADR 0012): unchanged.
- **Blog #2 / preprint reframe:** the negative result is the stronger narrative —
  measured a $36k bound, built the obvious fix, captured half on one panel, replication
  killed it, and the mechanism explains why. This honest-uncertainty arc supersedes the
  earlier "found a lever" framing.
- **Zenodo re-deposit (NEW, carry):** the adopted canonical data (ADR 0013) lives local
  + Zenodo v0.1 only, and v0.1 predates the rebuild. A v0.2 data deposit is a
  prerequisite for the preprint reproducibility claim — the committed audit JSONs cite
  numbers reproducible only against data not yet publicly pinned to match.
