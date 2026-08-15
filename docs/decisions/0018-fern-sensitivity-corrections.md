# ADR 0018 — Fern-exclusion sensitivity; Exhibit-2 basis correction; Jun 1–7 vintage restatement (W7)

**Status:** Accepted
**Date:** 2026-08-14 (W7 computation performed 2026-08-12)

---

## Context

ADR 0017 open thread 2 recorded a τ_p-excluding-Fern sensitivity as recommended follow-up.
W7 executed it under a pre-registered framing: **exactly one refit**, performed to characterize
a **retired** lever, with no outcome permitted to un-retire it.

Executing it surfaced two further items that belong in the same record: an error in ADR 0017's
own Exhibit 2, and a restatement of the Jun 1–7 panel baseline. This ADR consolidates all three.

Detail: `docs/results_w7_fern.md`, `data/audit/w7_fern.json`, `scripts/w7_fern_sensitivity.py`.

---

## (a) Correction to ADR 0017 Exhibit 2 — supersedes its §5 numbers

**The error, stated plainly.** ADR 0017 §5 / `results_w6_seasonal.md` Exhibit 2 described τ_p as
*"the q90 of realized RT MCPC over the train window"* and computed Fern's share of the
above-threshold mass on that basis. **This is wrong.** τ_p is the **q90 of the train DAM AS
quote** (5-min ffilled) — `scripts/backtest_w5a_eval.py:119` `_train_quote_q90` — and the ADR 0012
correction conditions on the **DAM quote level**, not on realized price.

**Corrected Fern shares of above-τ_p mass (DAM-quote basis):**

| Product | Corrected (DAM basis) | As published (realized basis) |
|---|---:|---:|
| regup | **30.4%** | 32.4% |
| rrs | **29.4%** | 2.7% |
| ecrs | **30.4%** | 12.6% |
| nspin | **48.4%** | 15.4% |

Fern remains 4/81 train days = **4.9% by duration**.

**The conclusion holds a fortiori.** ADR 0017 §5 concluded that "the frozen correction's trigger
level is materially set by a single named storm." On the correct basis that is *more* true and
far more uniform: 29–48% across all four products, rather than a 2.7–32.4% spread that made rrs
look unaffected. Nearly **half** of nspin's threshold-setting mass is one storm.

**ADR 0017's body is left unedited.** This ADR supersedes its §5 numbers and its one-line
description of τ_p. Editing 0017 in place would erase the record of what was published and what
the preprint may already have drawn from.

> **Guard — scope of this correction.** This does **not** touch the W5-R / W6 **panel-selection
> metric** (`qualifying interval = realized RT MCPC > τ_p, any product`,
> `scripts/backtest_w5r_run.py:13`). Comparing *realized* MCPC against the DAM-derived τ_p was a
> deliberate choice in the W5-R re-run design and **remains correct as specified**; every
> qualifying count published in W5-R, ADR 0014, W6 and ADR 0017 stands unchanged. The error was
> confined to Exhibit 2's *description* of τ_p and its share computation.

---

## (b) Fern-exclusion sensitivity (W7)

**One refit only.** Train window Jan 23 – Apr 13 (81 days) minus Fern (Jan 23–26) = **77 days**.
The W5-A fit procedure was imported verbatim — W7 defines no fitting logic of its own
(`_train_quote_q90`:119, `_fit_s`:151, `_proxy_high_bias`:131, `_build_proxy_cache`:108).

**Harness-fidelity control.** Re-running the *full* 81-day window through the same code
reproduces committed ADR 0012 exactly (τ 3.5600 / 2.7100 / 2.5600 / 14.9800; all four s_p to ten
decimal places). All movement below is attributable to Fern's exclusion, not to harness drift.

### Refit parameters

| Product | τ_p | τ_p′ | Δτ % | s_p | s_p′ | Δs % |
|---|---:|---:|---:|---:|---:|---:|
| regup | 3.560 | 3.060 | −14.0% | 0.15195465 | 0.25054932 | +64.9% |
| rrs | 2.710 | 2.610 | −3.7% | 0.00125885 | 0.11166382 | **+8,770%** |
| ecrs | 2.560 | 1.770 | −30.9% | 0.03746033 | 0.25305176 | +575.5% |
| nspin | 14.980 | 14.980 | +0.0% | 0.00000000 | 0.24615479 | from clamp |

Every τ′ ≤ τ; every s′ ≫ s — the correction becomes **markedly less aggressive** once the storm
leaves the fitting sample. rrs moves ~89×.

**nspin.** The severity of the fitted nspin response (clamped-to-zero, +$2.04/MW residual at the
floor) was a Fern artifact; a milder over-quote, consistent with the externally-identified
over-procurement mechanism (IMM report — still unverified, per ADR 0017 open thread 4), remains
in the non-storm data. Without Fern the fit returns an interior solution (s′ = 0.246,
`reason=ok`) rather than clamping.

### Four-panel re-run under (τ′, s′), frozen

| Panel | Committed Δ | Refit Δ′ | Sign |
|---|---:|---:|:--:|
| Apr 20–26 (eval, restated) | +18,270 | +16,377 | same |
| Apr 27–May 3 (scarcity, confirmatory) | +6,303 | +4,301 | same |
| Jun 1–7 (scarcity, primary) | −4,765 | −5,325 | same |
| May 4–10 (calm) | −10,619 | −12,637 | same |
| **Four-panel sum** | **+9,189** | **+2,716** | |

**Sign pattern preserved 4/4.** Baselines byte-matched the committed values on three panels; the
Jun 1–7 baseline did not, for reasons addressed in (c).

Two observations:

- **Fern flattered the lever.** The four-panel sum falls from +$9,189 to +$2,716 — wins shrink,
  losses deepen. Fern's presence in the training data made the lever look *better* than the
  non-storm fit supports, not worse.
- **Single-day concentration persists** under the refit: Apr 25 alone contributes +$21,873 of a
  +$16,377 eval-panel net, the same signature that sank the lever in W5-R.

### Pre-registered criterion

The fixed criterion "sign pattern across the four panels is unchanged" is **met**, mapping to:
*Fern shaped the parameters but not the conclusion.*

**ADR 0014 stands — the lever remains retired, and nothing here is grounds to revisit it.**
**ADR 0015 is strengthened on both axes:** single-episode dependence is now demonstrated in the
*fitting* data as well as the evaluation panels, and the negative out-of-sample conclusion
survives removal of that episode.

### Scope boundary

Fern was removed from the **fitting sample only**. The bootstrap analog pool starts 2026-01-09
and is strictly-before-target, so Fern days remain analog-pool members for every later target
day. This measures fitting-sample sensitivity, not full removal of Fern's influence.

---

## (c) Jun 1–7 vintage restatement (forward-only, ADR 0013 precedent)

**Restated:** the Jun 1–7 panel baseline is **87,532.86 → 87,174.46** (−$358.40, **0.41%**),
caused by the W6 June reassembly. `data/audit/w5r_run.json`'s Jun 1–7 baseline **no longer
reproduces**; the restated value is **canonical forward**. Consistent with ADR 0013, this is
recorded forward-only — no committed artifact is rewritten.

**Conclusions unchanged.** An added control (committed ADR 0012 parameters re-run on the current
vintage — no tuning, no new parameter values) isolates the two effects:

| Jun 1–7 configuration | Δ |
|---|---:|
| Committed params, old vintage (`w5r_run.json`) | −4,765 |
| Committed params, new vintage *(control)* | −4,760.04 |
| Refit params, new vintage | −5,324.58 |

→ **vintage effect on Δ = +$4.96** (negligible); refit effect = −$564.54. The W7 Δ-vs-Δ′
comparison is therefore attributable to the refit, and no W5-R or ADR 0014/0015 conclusion moves.

**What actually changed (cell-diff, backup verified against `SHA256SUMS_pre_w6.txt` before use).**
Across the Jun 1–7 panel window the reassembly changed **21 of 12,096 RT cells (0.174%)** — all
value-to-value revisions, **0 NaN filled, 0 values lost** — with `dam_prices` and
`system_conditions` **byte-identical** and row indices unchanged. The revisions are **scattered,
not concentrated**: 5 of 7 days, 6 columns, no contiguous run. A single LMP cell carries most of
the magnitude (2026-06-06 13:25, 55.92 → 99.95, **+$44.03**); every other revision is under $6.20.
That 0.17% of RT cells moved the panel baseline 0.41% is the quantitative record of how sensitive
a settled baseline is to ordinary upstream revision.

This closes the loop the ADR 0013 incident could not: that build was overwritten without a
backup, so the corresponding diff was unrecoverable. The pre-assembly backup rule made this one
answerable.

**Process rule (new, in force).** Post-reassembly no-regression checks **must cover every
committed panel baseline**, not only the April eval anchor. ADR 0017 §6's check was too narrow —
it verified the evening-peak bias and the eval baseline, and therefore missed a $358 shift in a
different panel. This rule closes that gap.

---

## Consequences

- ADR 0017 §5's Fern-share numbers and its description of τ_p are superseded by (a); its body
  stands unedited as the record of what was published.
- ADR 0014 stands. ADR 0015 stands and is strengthened.
- All W5-R / W6 qualifying counts and panel selections are unaffected (see the guard in (a)).
- The Jun 1–7 baseline is restated forward; W5-R's other three panel baselines still reproduce.
- Every future reassembly carries a broader no-regression obligation.

## Open threads

1. **Severe-summer test** — still open and pre-registered (Aug/Sep window). July 2026 did not
   supply a high-scarcity week.
2. **nspin** — a milder non-storm over-quote remains in the data; the IMM primary source
   (Potomac Economics, Dec 15 2025) is still **fetch-and-verify before citation**, per ADR 0017
   open thread 4.
3. **Fern in the analog pool** — Fern days remain analog-pool members for all targets. A
   pool-level exclusion would be a materially larger exercise and is **not scheduled**.
