# Data Directory

The raw and processed data files are **not committed to this repository**.

## Where to get the data

- **v0.1** (Dec 5, 2025 – Mar 31, 2026): Zenodo upload forthcoming (Week 2).
- **v1.0** (Dec 5, 2025 – Jun 5, 2026): In preparation.

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
