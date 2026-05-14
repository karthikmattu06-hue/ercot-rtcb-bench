# ADR 0001: Versioned Datasets (v0.1 before v1.0)

**Status:** Accepted
**Date:** 2026-05-13
**Author:** Karthik Mattu

---

## Context

The ERCOT RTC+B market launched on December 5, 2025. We have collected
post-launch market data through March 21, 2026 (raw SCED MCPC files) and
through April 2026 (processed energy/AS prices). The full target window for
the benchmark is December 5, 2025 through June 5, 2026 — six months of
post-launch data, which gives enough seasonal variation (winter → spring) and
enough regime time for algorithms to learn non-trivial strategies.

However, the April 1 – June 5 window has not yet been fetched and validated.
Waiting for the full dataset before publishing anything would delay the public
release by 4–6 weeks and block downstream work (baseline implementations,
blog posts, workshop paper drafting).

## Decision

Ship **v0.1** (December 5, 2025 – March 31, 2026) now, as a complete,
validated, documented release. Begin the April–June backfill in parallel.
Ship **v1.0** (December 5, 2025 – June 5, 2026) once the backfill is
validated and the schema is confirmed stable.

Semantic versioning communicates the intent:
- `v0.1` = first usable slice; schema may evolve
- `v1.0` = full benchmark window; schema is locked; Zenodo DOI assigned

## Rationale

**Ship early, extend later** is standard practice in open datasets. The
alternative — holding v0.1 until v1.0 is ready — risks:
1. Delaying feedback on schema design (early users find problems early)
2. Blocking blog post #1 and the dataset card, which reference the actual data
3. Creating a single large release that is harder to validate incrementally

The downside is that v0.1 users must upgrade their pipelines when v1.0 ships.
We mitigate this by:
- Documenting the schema explicitly in `docs/dataset-card.md`
- Promising backward compatibility in column names/types between v0.1 and v1.0
  (v1.0 extends coverage, does not change the schema)
- Using folder-name versioning (`data/processed/v0.1/`, `data/processed/v1.0/`)
  so both can coexist locally

## Cutoff dates

| Version | Start | End | Notes |
|---------|-------|-----|-------|
| v0.1 | 2025-12-05 06:00 UTC | 2026-03-31 23:55 UTC | Data in hand |
| v1.0 | 2025-12-05 06:00 UTC | 2026-06-05 23:55 UTC | Backfill in flight |

The start time 06:00 UTC = 00:00 CST (Central Standard Time), which is when
ERCOT's RTC+B market went live. All timestamps in the dataset are UTC.

## Known regime changes within v0.1

- **Jan 8, 2026**: ERCOT tightened the MIP optimality gap from ~2% to ~0.5%
  in the real-time co-optimization solve. This means the co-optimized dispatch
  solution quality improved mid-dataset. The `is_post_mip_tighten` flag in
  the processed tables marks intervals after this date.
- **Dec 5–11, 2025**: First week of RTC+B operation; operators and ERCOT were
  still calibrating. Price patterns in this window are atypically volatile.

Both are documented as known limitations in the dataset card.

## Upgrade path from v0.1 to v1.0

1. Download the v1.0 Parquet files from Zenodo (separate DOI, separate folder)
2. Update any hardcoded date ranges from `2026-03-31` to `2026-06-05`
3. Re-run validation to confirm no schema drift
4. The canonical train/val/test split will be extended in v1.0; see
   `docs/dataset-card.md` for the updated boundaries

## Alternatives considered

**Single release at v1.0**: Rejected — too long a delay, no early feedback.

**Rolling releases (v0.1, v0.2, v0.3…)**: Rejected — too much versioning
overhead for what is essentially one continuous time series being extended.
Two releases (v0.1, v1.0) is the right granularity.

**No versioning (just "latest")**: Rejected — reproducibility requires pinned
dataset versions. A benchmark paper that says "we used the data as of date X"
is not reproducible without a fixed, citable artifact.
