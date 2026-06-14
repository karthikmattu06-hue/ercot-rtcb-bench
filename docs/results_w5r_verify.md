# W5-R-verify — Baseline Re-Pin Verification

**Question:** is the +$2.53 rebuild shift a safe cosmetic re-pin (A), or a parameter-
perturbing partial-W5-A-redo? **Verdict: COSMETIC — re-pin is safe.** The W5-A fitted
parameters are byte-stable under the rebuild; the shift is confined to a few realized-AS
settlement cents in the eval window and does not move any fitted quantity.

---

## Verification 1 — Source stability / restatement direction → **Case 1 (source unchanged)**

`~/hybridbid` is a git repo. The upstream AS source `data/processed/as_prices/2026-04.parquet`:

- Has **exactly one committed version** (commit `cb4e2f7`); `git diff --quiet HEAD` on it
  **passes** — the working copy is **checksum-identical to the committed blob** and has
  not been modified since (mtime late-April, well before the May-16 forecaster build).
- The rebuilt forecaster Apr 20–26 MCPC matches this source **exactly** (0 mismatches,
  verified in W5-R-pull).

→ The source the May-16 build read is byte-identical to the source today. The
divergence is therefore on the **build** side: **the May-16 forecaster build diverged
from a stable upstream source; the rebuild corrects it.** Narrative: "prior build
divergent; rebuild restores faithfulness to source."

**Caveat (honest scope):** the May-16 *build output* was overwritten during assembly
(no pre-assembly backup), so the build's divergence cannot be diffed cell-by-cell. The
*direction* (build, not source) is established by source-checksum stability + the
rebuild-matches-source result; the exact build mechanism (a coalesce/priority or code
difference at May-16) is **not separately identified** and the ADR should say so rather
than over-claim a specific build bug.

---

## Verification 2 — Cosmetic vs parameter-perturbing → **COSMETIC**

### V2.1 — Scope of divergence (rebuilt vs May-16 build, by window)

May-16-build realized-AS means are recovered from the committed `w5a_diagnostic.json`
(the May-16 build's own stored stats); rebuilt means recomputed on current data.

| Window | Product | Rebuilt | Committed (May-16) | Δ ($/MW) |
|---|---|---:|---:|---:|
| train | regup | 1.5379 | 1.5380 | −0.00017 |
| train | rrs | 0.5466 | 0.5467 | −0.00011 |
| train | ecrs | 0.7425 | 0.7427 | −0.00015 |
| train | nspin | 2.1625 | 2.1629 | −0.00042 |
| val | regup | 0.9008 | 0.9009 | −0.00006 |
| val | rrs | 0.2147 | 0.2147 | 0.00000 |
| val | ecrs | 0.3607 | 0.3607 | +0.00001 |
| val | nspin | 1.2276 | 1.2276 | −0.00001 |

- Train/val realized-AS divergence is **sub-$0.0005/MW** (≤0.03% relative) on every
  product — a handful of slightly-different MCPC cells across 81 train days.
- The **DAM AS quote (the τ_p source) is unchanged exactly** (see V2.2 τ_p).
- **Eval window:** the divergence manifests as the **+$2 AS settlement revenue**
  (baseline $238,376.27 → $238,378.80; energy byte-identical). A per-cell eval
  comparison to the May-16 build is unavailable (build overwritten), but it is bounded
  by the same tiny magnitude as train/val and is — decisively — parameter-neutral (V2.2).

### V2.2 — Parameter stability (decisive)

W5-A fit recomputed on the **rebuilt** data (τ_p = train q90 DAM quote; s_p =
method-of-moments on high-regime E[max] bias), vs committed:

| Product | τ_p rebuilt | τ_p committed | s_p rebuilt | s_p committed | Δs_p |
|---|---:|---:|---:|---:|---:|
| regup | 3.5600 | 3.56 | 0.151955 | 0.151955 | **0.000000** |
| rrs | 2.7100 | 2.71 | 0.001259 | 0.001259 | **0.000000** |
| ecrs | 2.5600 | 2.56 | 0.037460 | 0.037460 | **0.000000** |
| nspin | 14.9800 | 14.98 | 0.000000 | 0.000000 | **0.000000** |

**All four (τ_p, s_p) are identical to committed to 6 decimal places (Δ = 0.000000).**
The micro-divergences in realized AS are far below the fit's sensitivity, and the DAM
quote (τ_p) is unchanged exactly.

### V2.3 — Verdict: **COSMETIC; re-pin is safe**

τ_p/s_p are unchanged to 6 sig figs (well beyond the ~4-sig-fig threshold), and the
divergence is confined to a few sub-cent realized-AS cells. Per the stated rule this is
**cosmetic**: re-pinning to the canonical-faithful rebuild is safe; only the **headline
revenue figures** shift ~$2–3 (0.001%). Because the parameters are unchanged, the W5-A
correction's behavior — the eval Δ structure and the 50.2% recovery — is preserved up to
that ~$2–3 baseline restatement (to be re-derived at re-pin time, not here). This is
**not** a partial W5-A redo.

---

## Backup discipline (logged for record)

The canonical forecaster parquets are gitignored (Zenodo-hosted) and were overwritten
during reassembly without a pre-assembly backup — the process miss that cost the
cell-level May-16 comparison. **Going forward: checksum-back-up the forecaster parquets
(sha256 manifest + copy) before any reassembly**, so a rebuild is always diffable
against the prior build.

**Files:** evidence reproduced inline (no new audit artifact). **HARD STOP** — the A/B
re-pin decision + ADR narrative happen in chat after review.
