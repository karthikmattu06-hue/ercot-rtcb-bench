# W5-R-pull — ERCOT Backfill Apr 27 – Jun 8, 2026

**Outcome:** the pull **succeeded** (data unblocked: 6 eligible weeks, was 0), but the
**no-regression sub-gate FAILED** — rebuilding the forecaster parquets shifted the
locked eval baseline by **+$2.53**. The shift is a *faithfulness correction*, not
corruption (the rebuild matches the canonical upstream source exactly; the prior
build did not). **STOP for a baseline-pinning decision before W5-R re-run.**

---

## Pull (resumable / atomic / throttled)

Driver `scripts/pull_w5r.py` reuses the proven `backfill_w3b` fetch + assembly and adds
the binding requirements the prior run lacked:

- **Completeness-based skip:** a *partial* cached day is re-pulled (in-day 5-min
  interval count ≥ 286 = complete), not treated as done — this repaired May 1/5/6 etc.
- **Atomic writes:** tmp + `os.replace` (never a half-written parquet).
- **Checkpoint + continue-past-hard-fail:** raw cache files are the checkpoint; a
  429/500 death costs only the in-flight day.
- **Schema-drift STOP:** column set checked against the established cache; no coercion.

**Result:** **225 pulled, 76 skipped (complete), 0 empty, 0 failed, 0 schema drift.**
No rate-limit deaths (the prior run's failure mode) — 2 s/request pacing held. Wall
clock ≈ 19 min.

Coverage (latest finite): RT prices **2026-06-09 04:55Z**, DAM **2026-06-09 04:00Z**,
system **2026-06-16 04:00Z**.

---

## Integrity gate — data eligibility (PASS on new weeks)

Per-week eligibility (≤0.5% per-series gap; tail = Sun+1 present). Qualifying counts use
the **τ_p metric** (realized AS effective price > correction boundary τ_p; the Q0
decision), not the prior q90-realized metric:

| Week | Worst gap | Eligible | τ_p qualifying / 2016 |
|---|---:|:---:|---:|
| Apr 27 – May 3 | 0.149% | ✅ | **341** |
| May 4 – 10 | 0.000% | ✅ | 187 |
| May 11 – 17 | 0.099% | ✅ | 200 |
| May 18 – 24 | 0.000% | ✅ | 234 |
| May 25 – 31 | 0.050% | ✅ | 280 |
| Jun 1 – 7 | 0.149% | ✅ | **376** |

**All 6 weeks eligible** (was 0). Apr 27–May 3 repaired from 1.98% → 0.149%. The data
requirement is **exceeded**: a scarcity panel (Jun 1–7 at 376, or Apr 27–May 3 at 341)
*and* a calm panel (May 4–10 at 187) are both available. (Selection is the W5-R re-run
chunk, not here.)

---

## No-regression gate — FAILED (but it's a correction, not corruption)

The locked eval baseline does **not** reproduce after the rebuild:

| | Energy | AS | Total |
|---|---:|---:|---:|
| Expected (committed) | $159,021 | $72,478 | **$238,376.27** |
| After rebuild | $159,021 | $72,480 | **$238,378.80** |
| Δ | $0 | +$2 | **+$2.53** (tol ±$1.00) |

Energy is byte-identical; the shift is **+$2 in AS** (0.001% of total). Diagnosis:

- I fetched **no** Apr 20–26 raw; upstream sources (hybridbid `as_prices` Apr 29,
  `energy_prices` Apr 18, raw rt_lmp/sced May 15) are **unchanged**.
- **The fresh forecaster Apr 20–26 MCPC matches the upstream canonical primary
  (`hybridbid as_prices`) EXACTLY** (verified, 0 mismatches). So the rebuild is
  *canonical-faithful*.
- Therefore the May-16 forecaster build — on which the committed `$238,376.27` was
  computed — was itself **slightly divergent from the upstream source** in April AS.
  Rebuilding to match source moved the baseline $2.53 (the AS forecast for Apr 20–26
  rides on April pool-day MCPC, which the rebuild corrected to canonical).

**This is not data corruption — it is a faithfulness correction that breaks exact
reproduction of all committed W4/W5 numbers.** Per the spec's binding no-regression
rule, the gate fails and W5-R is **not** declared unblocked until the baseline question
is resolved.

**Process miss:** I overwrote the May-16 forecaster parquets (April/May/June) during
assembly **without a pre-assembly backup**. The canonical May-16 build is no longer on
disk; restore source = Zenodo (the v0.1 dataset release) if exact reproduction is required.

---

## Decision required (research integrity — your call)

- **(A) Adopt the canonical-faithful rebuild; re-pin the baseline.** The rebuilt data
  matches the upstream source exactly, so it is arguably the *correct* data. Re-pin the
  locked baseline to **$238,378.80** (and re-derive the dependent W4/W5 figures, each
  shifting ~$2–3, 0.001%; no qualitative conclusion changes). Cleanest scientifically;
  documents that the prior build was non-canonical. The 6 eligible weeks are then ready
  for the W5-R re-run immediately.
- **(B) Restore the exact May-16 build from Zenodo; preserve exact reproduction.**
  Restore the canonical forecaster parquets, then patch ONLY the new dates (May 11–Jun 8
  + the Apr 27–30 repair) **without rebuilding Apr 1–26**, so the eval stays
  byte-identical and every committed number reproduces. Preserves the locked panel at
  the cost of keeping a build that diverges from the upstream source by ~$2.

Either way, the **raw data pull is sound and complete** — the only open item is which
forecaster-parquet build to pin.

**Files:** `scripts/pull_w5r.py`, pull log `data/audit/w5r_pull_log.json`, coverage +
regression `data/audit/w5r_pull_coverage.json`. (Forecaster parquets are gitignored —
Zenodo-hosted — so not in the commit.)

**HARD STOP** — baseline-pinning decision (A/B) in chat before the W5-R re-run.
