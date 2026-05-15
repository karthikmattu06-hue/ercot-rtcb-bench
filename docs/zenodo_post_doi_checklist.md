# Post-Zenodo DOI Swap Checklist

After the Zenodo upload completes and a DOI is minted, update the three
locations below and push a single commit. The DOI format is
`10.5281/zenodo.NNNNNNN`.

## 1. `CITATION.cff`

Replace the current file with:

```yaml
cff-version: 1.2.0
title: "ercot-rtcb-bench v0.1: Post-RTC+B ERCOT Market Data for Battery Bidding Benchmarks"
authors:
  - family-names: Mattu
    given-names: Karthik
    affiliation: "Rochester Institute of Technology"
date-released: <YYYY-MM-DD>
version: "0.1"
license: Apache-2.0
repository-code: https://github.com/karthikmattu06-hue/ercot-rtcb-bench
abstract: >
  117-day open benchmark dataset for BESS bidding under ERCOT's RTC+B
  market design (Dec 5, 2025 – Mar 31, 2026). Includes RT/DAM prices,
  AS clearings, per-product ASDC breakpoints, and NPRR1268-verified
  oracle reconstruction.
identifiers:
  - type: doi
    value: <ZENODO_DOI_HERE>
    description: Zenodo deposit for v0.1 dataset
keywords:
  - energy storage
  - battery bidding
  - ERCOT
  - electricity markets
  - ancillary services
  - RTC+B
  - benchmark dataset
```

## 2. `docs/dataset-card.md` — Citation section

Replace the `## Citation` section (currently lines ~322–334) with:

```markdown
## Citation

Cite this dataset as:

> Mattu, K. (<YYYY>). *ercot-rtcb-bench v0.1: Post-RTC+B ERCOT Market
> Data for Battery Bidding Benchmarks (Dec 5, 2025 – Mar 31, 2026)*
> [Data set]. Zenodo. https://doi.org/<ZENODO_DOI_HERE>

DOI: [<ZENODO_DOI_HERE>](https://doi.org/<ZENODO_DOI_HERE>)

See also `CITATION.cff` in the repository root.
```

## 3. `docs/dataset-card.md` — Versions table

Update the v0.1 row in the `## Versions` table to include the DOI:

```markdown
| **v0.1** | 2025-12-05 – 2026-03-31 | <YYYY-MM-DD> | [![DOI](https://zenodo.org/badge/DOI/<ZENODO_DOI_HERE>.svg)](https://doi.org/<ZENODO_DOI_HERE>) |
```

## 4. `README.md` — Add DOI badge

Near the top of the repo README (after the title/description, before the
first section header), add:

```markdown
[![DOI](https://zenodo.org/badge/DOI/<ZENODO_DOI_HERE>.svg)](https://doi.org/<ZENODO_DOI_HERE>)
```

## 5. Single commit

```bash
git add CITATION.cff docs/dataset-card.md README.md
git status  # confirm exactly these three files

git commit -m "docs: v0.1 Zenodo DOI <ZENODO_DOI_HERE>

Published to Zenodo on <YYYY-MM-DD>:
https://doi.org/<ZENODO_DOI_HERE>

Updates CITATION.cff, dataset-card.md §Citation/§Versions, README badge.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push origin main
```

## 6. Verify DOI resolves

```bash
curl -sI "https://doi.org/<ZENODO_DOI_HERE>" | head -5
# Expected: HTTP/2 302 (or 301) redirecting to https://zenodo.org/records/...
```

Note: DOI propagation can take a few minutes after publishing. If it
doesn't resolve immediately, wait 5 minutes and retry.
