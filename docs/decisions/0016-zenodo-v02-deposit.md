# ADR 0016 — Zenodo v0.2 re-deposit (canonical data publicly pinned)

**Status:** Accepted (draft deposited; awaiting human Publish)
**Date:** 2026-07-03

---

## Context

Every committed audit number (`w5a`, `w5r`, `w5b_precheck`) is computed against the ADR
0013 canonical-faithful rebuild (+ the W5-R backfill pull through Jun 8, 2026), which
existed only locally and in Zenodo v0.1 — but v0.1 **predates** that rebuild and no longer
reproduces the current baseline ($238,376.27 vs the re-pinned $238,378.80). The preprint
cannot claim reproducibility until the canonical dataset is publicly pinned.

## Decision

Deposit the canonical **forecaster-input** parquets as **Zenodo v0.2**, a new version of
the existing record (concept DOI preserved; v0.1 stays citable as historical).

- **Concept DOI:** `10.5281/zenodo.20204993` (always resolves to latest)
- **v0.2 version DOI:** `10.5281/zenodo.21178739`
- **v0.1 version DOI:** `10.5281/zenodo.20204994` (historical; related as `isNewVersionOf`)
- **Pinned code commit:** `66775259caab91f3c7793dbea0ae0956e32fc86d`

**Contents.** 18 monthly parquets (2026-01…2026-06), flat-named `<series>_<YYYY-MM>.parquet`
for `rt_prices` (RT LMP + AS MCPC ×5), `dam_prices` (DAM SPP + AS MCPC ×5), and
`system_conditions` (load/wind/solar/net-load); RT/DAM finite through 2026-06-09 UTC. Plus
`SHA256SUMS.txt` (sha256 manifest) and a self-contained `reproduce.py`.

**Reproduction proof (decisive, pre-publish).** From the packaged copies only
(reconstructed in a temp dir, machine-local data path blocked), the committed baseline
path reproduces the canonical anchor:

```
Stochastic LP eval panel (Apr 20-26, 2026; seed 42; AS anchor correction OFF)
    ==>  $238,378.80229    (target $238,378.80, drift +$0.00229, tol +/- $1.00)
    Components: Energy $159,020.79 / AS $72,480.28 / Liq $6,877.73   GATE: PASS
```

**Not a superset.** v0.2 re-pins the forecaster-input parquets and extends RT/DAM coverage
through Jun 9, 2026, but does **not** carry the Dec 5–31, 2025 span or the auxiliary v0.1
tables (`as_clearing`, `asdc_hourly`, `asdc_params`, `as_plan`); overlapping months are
rebuilt, not byte-identical to v0.1. Cite v0.1 for the historical span/auxiliary tables;
cite **v0.2** as the reproduction target for the committed baseline/audit numbers.

## Consequences

- Reproduction instructions point at **v0.2** (concept DOI for latest); v0.1 references are
  retained only as historical.
- Backup-discipline rule (ADR 0013) satisfied for the public artifact: sha256 manifest
  shipped in the deposit; on-disk uploads md5-verified against local copies.

## Provenance note

Prepared under the `zenodo_v02_chunk.md` plan with a hard paste-back gate before publish.
The Zenodo record is deposited as an **unsubmitted draft**; the DOI is minted only when a
human clicks **Publish** in the Zenodo web UI (publishing is irreversible). Supersedes no
prior ADR; carries the ADR 0013 re-pin into the public deposit.
