# Data Directory

The raw and processed data files are **not committed to this repository**.

## Where to get the data

- **v0.2** (Jan 1 – Jun 9, 2026) — **canonical reproduction target**, published:
  https://doi.org/10.5281/zenodo.21178739
- **v0.1** (Dec 5, 2025 – Mar 31, 2026) — historical, published:
  https://doi.org/10.5281/zenodo.20204994
- **v1.0** (Dec 5, 2025 – Jun 5, 2026): In preparation.

Concept DOI (always latest): https://doi.org/10.5281/zenodo.20204993

Note: v0.2 is **not** a strict superset of v0.1 — it drops the Dec 2025 span and the
auxiliary tables (`as_clearing`, `asdc_hourly`, `asdc_params`, `as_plan`). Use v0.1
for those.

## Reproducing the data locally

To reproduce the v0.1 dataset from ERCOT public APIs:

```bash
# Requires ERCOT API credentials in .env (see .env.example)
bash scripts/fetch_v0_1.sh
```

To reproduce the v1.0 dataset (adds Apr 1 – Jun 5, 2026):

```bash
bash scripts/fetch_v1_0.sh
```

## Directory structure (after running fetch scripts)

```
data/
├── raw/            ERCOT API dumps (daily Parquet per product)
├── processed/
│   ├── v0.1/       Canonical v0.1 tables (monthly Parquet per table)
│   └── v1.0/       Canonical v1.0 tables (forthcoming)
├── audit/          Coverage manifests and fetch logs
└── validation/     Validation reports
```

## Schema

See `docs/dataset-card.md` for the full schema, data splits, and known
limitations.
