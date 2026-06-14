> Superseded by results_w5r_run.md / ADR 0013; retained for provenance

# W5-R Results: Two-Panel Replication of the AS Anchor Shrinkage — **Phase 0 STOP**

**Scope:** out-of-sample replication of the frozen W5-A correction (ADR 0012) on two
new panels. No refit, no code changes. **Outcome: STOP at Phase 0 — no eligible
candidate week exists; data ingestion is the prerequisite.**

---

## Housekeeping

`w4a-attribution` branch deleted (fully merged; `git branch -d`).

## Frozen correction — verified identical to ADR 0012

Read directly from the committed `data/audit/w5a_eval.json` (not re-typed, not refit):

| Product | τ_p | s_p |
|---|---:|---:|
| regup | 3.560 | 0.15195465 |
| rrs | 2.710 | 0.00125885 |
| ecrs | 2.560 | 0.03746033 |
| nspin | 14.980 | 0.00000000 |

Matches the ADR 0012 values (regup 3.56/0.152, rrs 2.71/0.001, ecrs 2.56/0.038,
nspin 14.98/0.000).

---

## Phase 0 — Recon + integrity

### Data coverage (latest **finite** timestamp, not parquet index extent)

| Series | Latest finite data |
|---|---|
| RT prices (LMP + 5× MCPC) | **2026-05-11 04:55 UTC** |
| DAM AS MCPC | **2026-05-11 04:00 UTC** |
| System (net load) | 2026-05-18 04:00 UTC |

**Finding (data integrity):** the monthly parquets are **indexed through May 31 but
NaN-padded after ~May 11** — RT and DAM AS data effectively end mid-day **May 11,
2026**. The row count (8,928 = 31×288) is misleading; the *finite* data is the binding
constraint. RT/DAM are the limiting series (net load reaches May 18).

### Leakage check

Analog pool is **dynamic, strictly-before-target**: `[2026-01-09, target_day)`. For a
target day in late April / May it includes the prior W5-A train/val/eval days as pool
members — legitimate (strictly before, realized analogs), **leakage-safe**. The
correction parameters are **frozen** from the W5-A train fit (no refit), so the
selection and runs cannot see panel data. Pool size grows for later weeks (more
analogs, generally better forecast quality). Convention reported per spec; both arms
(pool, params) are leakage-safe.

### Train top-decile thresholds (selection metric)

**Discrepancy flagged:** `data/audit/w5a_diagnostic.json` does **not** store a
per-product realized-price threshold (it holds bias stats, LMP-quartile cuts, and a
revenue-weighted concentration share — no q90 of realized AS price). The spec's "train
top-decile threshold per product" is therefore **recomputed** here as the q90 of
realized RT MCPC per product on the W5-A train window (Jan 23–Apr 13) — the faithful
reading:

| Product | q90 realized MCPC ($/MW) |
|---|---:|
| regup | 2.650 |
| rrs | 0.730 |
| ecrs | 0.880 |
| nspin | 3.744 |

### Candidate weeks + integrity

Mon–Sun weeks from Apr 27, within finite coverage. The candidate enumeration stops at
the first week with an absent day (May 11–17: May 12+ absent).

| Week | Worst per-series gap | Tail data | Eligible | Note |
|---|---:|---|:---:|---|
| 2026-04-27 – 05-03 | **1.98%** | present (May 4) | **No** | gaps > 0.5% rule |
| 2026-05-04 – 05-10 | **3.47%** | present (May 11) | **No** | gaps > 0.5% rule |

Per-series missing intervals (genuine RT gaps, not imputation artifacts):

- **Apr 27–May 3:** LMP 13 (0.64%); each MCPC 40 (1.98%).
- **May 4–10:** LMP 36 (1.79%); each MCPC 70 (3.47%).

Both weeks exceed the pre-registered **0.5%** per-series gap threshold on every MCPC
series → **ineligible**. No complete Mon–Sun week after Apr 26 falls within clean
coverage (the next week, May 11–17, is almost entirely absent).

---

## Decision — Phase 0 STOP

**No eligible candidate week exists.** Per the pre-registered Phase 0 rule ("If
coverage ends before any complete post-Apr-26 week exists → STOP"; "flag any week
>0.5% gaps as ineligible"), the chunk stops here. The gaps are imputable by the
harness, but the pre-registered rule is binding — **I am not deviating to run an
ineligible week** (that would move the goalpost the replication was designed to test).

No panels were run; no LP/forecaster/ADR changes were made.

---

## Context (not selection — both weeks ineligible)

For auditability, qualifying-interval counts on the (ineligible) candidate weeks:

| Week | Qualifying / total | regup | rrs | ecrs | nspin |
|---|---:|---:|---:|---:|---:|
| Apr 27–May 3 | **593 / 2016 (29.4%)** | 294 | 393 | 423 | 474 |
| May 4–10 | **303 / 2016 (15.0%)** | 84 | 237 | 276 | 281 |

The available (partial) weeks were **not calm** — Apr 27–May 3 in particular was a
high-scarcity week (29% of intervals above train q90). So the blocker is purely **data
availability**, not an absence of scarcity to test against. Had the data been clean,
Apr 27–May 3 would have been a strong scarcity-panel candidate; a calm panel would have
required ingestion further into May/June.

---

## What unblocks W5-R

Data ingestion of RT prices, DAM AS MCPC, RT LMP, and net load through **at least one
complete, ≤0.5%-gap Mon–Sun week after Apr 26 containing a scarcity day** (and ideally
a calm week, to test the ADR 0012 under-commitment risk directly). Current ingestion
ends ~May 11; a single additional clean week would enable the scarcity arm, two would
enable both arms. Until then the +$18,271 / 50.2% W5-A result remains a **single-panel**
finding and should not be claimed in v0.2/preprint (per ADR 0012).

**Files:** `scripts/backtest_w5r.py`; audit `data/audit/w5r_replication.json`.

**HARD STOP** — ingestion-prerequisite decision happens in chat.