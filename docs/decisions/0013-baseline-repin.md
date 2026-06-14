# ADR 0013 — Baseline re-pin to canonical-faithful build (W5-R data adoption)

**Status:** Accepted
**Date:** 2026-06-13

---

## Context

The W5-R data pull (ERCOT backfill Apr 27 – Jun 8, 2026) repaired the ingestion gaps
that had stopped W5-R replication (local RT/DAM data previously truncated at ~May 10).
Reassembling the forecaster parquets to incorporate the pull triggered the
no-regression check: the locked Stochastic-LP eval baseline (Apr 20–26) moved
**$238,376.27 → $238,378.80 (+$2.53)**. The shift is **AS-only**; energy revenue is
**byte-identical** ($159,021).

Two verifications (W5-R-verify, `docs/results_w5r_verify.md`) characterized it:

- **V1 — source stability (git-checksum).** The upstream AS source
  (`~/hybridbid/data/processed/as_prices/2026-04.parquet`) has a single committed
  version (commit `cb4e2f7`) and a clean working tree (`git diff --quiet HEAD` passes),
  unchanged since late April — before the May-16 forecaster build. The rebuild matches
  this source exactly (0 mismatches on Apr 20–26 MCPC). The honest characterization is:
  **divergence between the May-16 build and a stable upstream source; direction is
  build-side; exact mechanism not separately identified (May-16 output overwritten
  without backup → not cell-diffable).** No specific build bug is asserted.

- **V2 — cosmetic, not parameter-perturbing.** Realized-AS divergence between the
  rebuild and the May-16 build is **≤ 0.0004 $/MW across the entire train window**
  (≈0 in val); the DAM AS quote is unchanged exactly. The W5-A fitted parameters
  recomputed on the rebuilt data are **identical to the committed values to 6 decimal
  places** (τ_p: 3.5600 / 2.7100 / 2.5600 / 14.9800; s_p: 0.151955 / 0.001259 /
  0.037460 / 0.000000; Δs_p = 0.000000 on all four products). Only the eval revenue
  restates ~$2–3.

---

## Decision

1. **Adopt the canonical-faithful rebuild as the pinned dataset.** It matches the
   stable upstream source exactly and leaves every W5-A parameter byte-identical.

2. **New baseline anchor: Stochastic LP = $238,378.80** (eval Apr 20–26), effective
   ADR 0013 forward. Energy $159,021 (unchanged); AS $72,480; the +$2 is AS settlement.

3. **Supersedes note.** *ADRs 0010–0012 reference the pre-rebuild baseline $238,376.27
   and figures computed on it; as of ADR 0013 the canonical baseline is $238,378.80.
   Prior ADRs are unedited historical record; the shift is +$2.53 (0.001%) and changes
   no qualitative finding, parameter, or ordering.*

4. **W5-A lever restated forward (cosmetic only).** Because the (τ_p, s_p) are
   unchanged, the W5-A eval Δ (+$18,271) and the 50.2% recovery of the $36,393 oracle
   bound are preserved up to the ~$2 baseline restatement. W5-A is **not** recomputed or
   redone here; this is a forward note, not a re-run.

5. **Forward-only.** ADRs 0010–0012 and their figures are **not edited**. They stand as
   the historical record of the pre-rebuild build; ADR 0013 carries the supersession.

---

## Consequences

- **W5-R is data-unblocked.** All six Mon–Sun weeks Apr 27 – Jun 7 are now eligible
  (≤0.5% per-series gap; Apr 27–May 3 repaired 1.98% → 0.149%); coverage runs through
  Jun 9. The two-panel replication requirement (≥1 scarcity + ≥1 calm) is satisfiable —
  under the τ_p metric, scarcity candidates Jun 1–7 (376 qualifying) / Apr 27–May 3
  (341) and calm candidate May 4–10 (187).
- **Headline-number restatement.** Any future citation of the eval baseline uses
  $238,378.80; W4/W5 figures derived from $238,376.27 shift by ~$2–3 (0.001%) and are
  not re-issued (forward-only).

## Backup discipline (rule in force)

The W5-R reassembly overwrote the gitignored, Zenodo-hosted forecaster parquets
**without a pre-assembly backup**, which cost the cell-level comparison against the
May-16 build (only the direction, not the mechanism, of the divergence could be
established). **Rule, effective now: before any reassembly of the forecaster parquets,
write a sha256 manifest and a copy of the current parquets**, so a rebuild is always
diffable against the prior build. This precedent is the reason.

## Open threads (carried forward, unchanged)

- **nspin anchor over-quote** (ADR 0012): nspin DAM exceeds realized even at its q90
  floor (s_p clamped to 0, +$2/MW residual) — an anchor-level issue beyond shrinkage.
- **W5-R replication**: pending but now unblocked (data ready); runs in the next chunk
  on a fresh branch. Until it completes, the W5-A lever remains single-panel (not
  v0.2/preprint-claimable per ADR 0012).
- **W5-B (LMP evening-peak mean fix, ~$21.5k)**: the next bankable lever after W5-R.
