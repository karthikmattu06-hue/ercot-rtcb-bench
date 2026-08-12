# W7 Results — Fern-Exclusion Sensitivity of the W5-A Fitted Structure

**Chunk:** W7 · **Branch:** `w7-fern-sensitivity` · **Date:** 2026-08-12
**Scope:** exactly ONE refit — the W5-A procedure re-run on train-minus-Fern.

> **This characterizes a retired lever. No outcome here un-retires it. ADR 0014 stands.**
> Everything below is fitting-data sensitivity, nothing more.

Artifacts: `data/audit/w7_fern.json`, `scripts/w7_fern_sensitivity.py`.

---

## Procedure provenance (no drift)

The fit logic is imported verbatim; W7 defines none of its own:

| Quantity | Source |
|---|---|
| τ_p = q90 of train DAM AS quote (5-min ffilled) | `scripts/backtest_w5a_eval.py:119` `_train_quote_q90` |
| s_p = bisection method-of-moments on high-regime E[max] bias | `scripts/backtest_w5a_eval.py:151` `_fit_s` |
| high-regime effective bias | `scripts/backtest_w5a_eval.py:131` `_proxy_high_bias` |
| train-day reconstruction cache | `scripts/backtest_w5a_eval.py:108` `_build_proxy_cache` |
| panel runner | `scripts/backtest_w5r.py` `run_panel` |

**Fern window:** Jan 23–26, 2026 · train window Jan 23–Apr 13 = 81 days → **77 days** after exclusion.

### Control — harness fidelity

Re-running the *full* train window through the same code reproduces committed ADR 0012 exactly:

| Product | τ recomputed | τ committed | s recomputed | s committed | |
|---|---:|---:|---:|---:|:--:|
| regup | 3.5600 | 3.560 | 0.1519546509 | 0.1519546509 | ✅ |
| rrs | 2.7100 | 2.710 | 0.0012588501 | 0.0012588501 | ✅ |
| ecrs | 2.5600 | 2.560 | 0.0374603271 | 0.0374603271 | ✅ |
| nspin | 14.9800 | 14.980 | 0.0000000000 | 0.0000000000 | ✅ |

Any movement below is attributable to Fern's exclusion, not to harness drift.

---

## Phase 1 — Refit on train-minus-Fern

| Product | τ_p | τ_p′ | Δτ | Δτ % | s_p | s_p′ | Δs % |
|---|---:|---:|---:|---:|---:|---:|---:|
| regup | 3.560 | **3.060** | −0.500 | **−14.0%** | 0.15195465 | **0.25054932** | **+64.9%** |
| rrs | 2.710 | 2.610 | −0.100 | −3.7% | 0.00125885 | **0.11166382** | **+8,770%** |
| ecrs | 2.560 | **1.770** | −0.790 | **−30.9%** | 0.03746033 | **0.25305176** | **+575.5%** |
| nspin | 14.980 | 14.980 | +0.000 | +0.0% | 0.00000000 | **0.24615479** | n/a (from clamp) |

**The fitted structure is heavily Fern-dependent.**

- Every threshold falls or holds; ecrs drops 31%, regup 14%.
- Every shrink factor rises sharply — the correction becomes **much less aggressive**
  (larger s = less shrinkage toward τ) once the storm is out of the fitting sample.
- **rrs moves ~89×** (0.0013 → 0.1117): its near-total shrink was almost entirely a Fern artifact.
- **nspin's `clamped_zero` unclamps.** ADR 0012 recorded nspin as pinned to τ with a residual
  over-quote it could not fix — an open thread. Without Fern the fit returns a normal interior
  solution (s′ = 0.246, `reason=ok`). **The nspin clamp pathology was Fern-driven.**

### Crossing mass — Fern share of above-threshold intervals (full train window)

Fern is **4/81 train days = 4.9% by duration**.

| Product | Above-τ (DAM-quote basis) | Fern share | Above-τ (realized-MCPC basis) | Fern share |
|---|---:|---:|---:|---:|
| regup | 2,328 | **30.4%** | 1,760 | 32.4% |
| rrs | 2,328 | **29.4%** | 828 | 2.7% |
| ecrs | 2,328 | **30.4%** | 1,100 | 12.6% |
| nspin | 1,092 | **48.4%** | 762 | 15.4% |

> ### ⚠️ Correction to ADR 0017 / `results_w6_seasonal.md` Exhibit 2
>
> Exhibit 2 stated *"τ_p is the q90 of realized RT MCPC over the train window"* and computed
> Fern's share on that basis (32.4% / 2.7% / 12.6% / 15.4%). **That basis is wrong.** τ_p is
> the q90 of the train **DAM AS quote** (`_train_quote_q90`, line 119) — the correction is
> conditioned on the DAM quote level (ADR 0012), not on realized price.
>
> On the correct DAM-quote basis the Fern shares are **30.4% / 29.4% / 30.4% / 48.4%**.
>
> **The disclosure gets stronger and more uniform, not weaker.** The headline regup figure
> barely moves (32.4% → 30.4%), but rrs goes from a reassuring 2.7% to **29.4%** and nspin
> from 15.4% to **48.4%** — nearly half of nspin's threshold-setting mass is one storm.
> ADR 0017 §5's conclusion ("the frozen correction's trigger level is materially set by a
> single named storm") holds *a fortiori*; only its supporting numbers and the one-line
> description of what τ_p is need correcting. Flagged here; ADR 0017 is merged, so the fix
> is a decision for chat.

---

## Phase 2 — Four committed W5-R panels under (τ′, s′)

Frozen at the refit values; no further tuning.

### Baseline byte-match check (flag OFF — must be independent of τ, s)

| Panel | Baseline now | Committed | Drift | |
|---|---:|---:|---:|:--:|
| Apr 20–26 (eval) | 238,378.80 | 238,378.80 | +0.00229 | ✅ MATCH |
| Apr 27–May 3 | 321,419.73 | 321,419.73 | +0.00087 | ✅ MATCH |
| **Jun 1–7** | **87,174.46** | **87,532.86** | **−358.40** | ❌ **MISMATCH** |
| May 4–10 (calm) | 60,388.34 | 60,388.34 | +0.00063 | ✅ MATCH |

**The Jun 1–7 mismatch is a data-vintage effect, not a refit effect** — it is the W6 June
reassembly (ADR 0017 §6) showing up in revenue. An added control (committed params re-run on
the current vintage; no tuning) isolates it:

| Jun 1–7 configuration | Δ |
|---|---:|
| Committed params, **old** vintage (`w5r_run.json`) | −4,765 |
| Committed params, **new** vintage *(added control)* | **−4,760.04** |
| Refit params, new vintage | **−5,324.58** |

→ vintage effect on Δ = **+$4.96** (negligible); refit effect = **−$564.54**. The Δ comparison
below is therefore interpretable, but note the *baseline* moved $358 (0.41%), which ADR 0017 §6
did not capture — it checked only the evening-peak bias and the April eval baseline.

### Δ committed vs Δ′ refit

| Panel | Committed Δ | Refit Δ′ | Change | Sign |
|---|---:|---:|---:|:--:|
| Apr 20–26 (eval, restated) | +18,270 | **+16,377** | −1,893 | same |
| Apr 27–May 3 (scarcity, confirmatory) | +6,303 | **+4,301** | −2,002 | same |
| Jun 1–7 (scarcity, primary) | −4,765 | **−5,325** | −560 | same |
| May 4–10 (calm) | −10,619 | **−12,637** | −2,018 | same |
| **Four-panel sum** | **+9,189** | **+2,716** | **−6,473** | |

**Sign pattern preserved on 4/4 panels.**

Per-day Δ′ and worst days:

| Panel | Worst day | Per-day Δ′ |
|---|---|---|
| Apr 20–26 | 04-24 −8,647 | +1,322 · +955 · −1,162 · +1,069 · **−8,647** · **+21,873** · +453 |
| Apr 27–May 3 | 04-27 −14,745 | **−14,745** · **+21,038** · +5,160 · −7,511 · +1,836 · +3,167 · −683 |
| Jun 1–7 | 06-04 −8,691 | −36 · +505 · +5,551 · **−8,691** · −2,513 · +1,813 · −2,207 |
| May 4–10 | 05-05 −7,498 | +2,228 · −7,498 · −6,452 · +5,240 · −2,258 · −2,121 · +4,938 |

Single-day concentration persists under the refit — Apr 25 still carries +$21,873 of a
+$16,377 panel net.

---

## Interpretation against the fixed criteria

**Criterion met: "sign pattern across the four panels is unchanged."** 4/4 panels keep their
sign. Per the pre-registered mapping:

> *Fern shaped the parameters but not the conclusion; ADR 0015's single-episode-dependence
> claim gains a "conclusion robust to the storm's exclusion" note.*

### Summary paragraph — mapping onto ADR 0015 / 0017

Winter Storm Fern set the fitted structure to a degree that is larger than ADR 0017 disclosed:
excluding four storm days from an 81-day training window moves every threshold down (ecrs
−31%, regup −14%), moves every shrink factor up sharply (rrs ~89×, ecrs +576%, regup +65%),
and **dissolves the nspin `clamped_zero` pathology that ADR 0012 carried as an open thread**.
On the correct DAM-quote basis, Fern supplies 29–48% of the above-threshold mass that defines
τ_p while being 4.9% of the window by duration. **Yet the conclusion is unmoved:** re-running
the four pre-registered W5-R panels under the Fern-excluded parameters preserves the sign
pattern 4/4 — the lever still wins on the eval and confirmatory panels, still loses on the
most-scarce panel and on the calm panel. If anything the Fern-excluded fit is *worse*: the
four-panel sum falls from +$9,189 to +$2,716, wins shrink and losses deepen, so Fern's
presence in the training data **flattered** the lever rather than handicapping it. This
strengthens ADR 0015 on both axes — the fitted parameters are shown to be single-episode
dependent in the *fitting* data, and the negative out-of-sample conclusion survives removing
that episode. **ADR 0014's retirement stands, and nothing here is grounds to revisit it.**

### Scope boundary (reported, not worked around)

Fern was removed from the **fitting sample only**. The bootstrap analog pool starts 2026-01-09
and is strictly-before-target, so Fern days remain analog-pool members for every later target
day. This measures fitting-sample sensitivity, not full removal of Fern's influence from the
system. A pool-level exclusion would be a materially larger change and was not attempted.

## What this chunk did not do

One refit only (train-minus-Fern). No other parameter tuning, no new correction form, no ADR,
not merged. The added Jun 1–7 control re-ran committed parameters — it introduced no new
parameter values.
