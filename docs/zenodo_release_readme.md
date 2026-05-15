# ercot-rtcb-bench v0.1

**ERCOT Post-RTC+B Open Benchmark Dataset**

This is the v0.1 release of the `ercot-rtcb-bench` open benchmark for
battery energy storage system (BESS) bidding under ERCOT's Real-Time
Co-optimization Plus Batteries (RTC+B) market design, effective
December 5, 2025.

## Coverage

- **Window:** December 5, 2025 – March 31, 2026 (117 operating days)
- **Markets:** ERCOT Real-Time Market (RT) and Day-Ahead Market (DAM)
- **Products:** Energy + 5 Ancillary Services (Reg-Up, Reg-Down, RRS, ECRS,
  Non-Spin) with NPRR1268-verified per-product ASDCs

## What's inside

Tabular data in Parquet format under `data/v0.1/`:

| Table | Description | Rows |
|-------|-------------|------|
| `rt_prices/` | 5-min RT LMPs and MCPCs per settlement point | 33,624 |
| `dam_prices/` | Hourly DAM SPPs and MCPCs (Non-Spin split per ADR 0004) | 2,796 |
| `as_clearing/` | 5-min per-resource AS award and clearing records | 152,260 |
| `system_conditions/` | 5-min load and renewables actuals/forecasts | 33,624 |
| `asdc_hourly/` | Realized per-product ASDC breakpoints from np4-212-cd | 21,650,559 |
| `asdc_params.parquet` | AORDC regression-fit parameters (static, 5 rows) | 5 |
| `as_plan/` | Hourly AS Plan quantities from np4-33-CD | 2,807 |

Documentation under `docs/`:

- `dataset-card.md` — full schema, sources, license, known limitations
- `decisions/` — ADRs 0001 through 0006
- `validation/` — coverage notes and oracle validation reports

## Quickstart

```python
import pandas as pd
from pathlib import Path

# Load all RT prices
rt = pd.concat(
    pd.read_parquet(p)
    for p in sorted(Path("data/v0.1/rt_prices").glob("*.parquet"))
)
print(rt.dtypes)
print(rt.head())

# Load ASDC breakpoints for a single day
asdc_day = pd.read_parquet("data/v0.1/asdc_hourly/2026-02-15.parquet")
print(asdc_day.groupby("as_product")["segment_index"].max())
```

## NPRR1268 oracle verification

The per-product ASDC breakpoints in `asdc_hourly/` have been verified against
the NPRR1268 §4.4.12 disaggregation formula. All four upward products
(RegUp, RRS, ECRS, Non-Spin) pass a mean price-error threshold of ≤$0.10/MW-h
across all 117 days. See `docs/validation/asdc_oracle_summary.md` for details.

## Code and baselines

The code behind this dataset — ingest scripts, NPRR1268 formula implementation,
and MILP baselines — lives in the GitHub repository:

**https://github.com/karthikmattu06-hue/ercot-rtcb-bench**

The repository includes:
- `src/ercot_rtcb_bench/` — data ingest, schema, ASDC formula
- `scripts/` — build, fetch, and validation scripts
- `methods/` — perfect-foresight and point-forecast LP baselines

## License

Code is released under **Apache-2.0** (see `LICENSE`). The underlying ERCOT data
is sourced from public data products under ERCOT's data usage terms; see
`docs/dataset-card.md` §11 for the full license discussion.

## Citation

See `CITATION.cff` for the machine-readable citation. This deposit is the
citable artifact for the v0.1 dataset.

## Known limitations

See `docs/dataset-card.md` §10 for the full list. Key points:
- AS clearing data covers through March 21 only (last 10 days of March missing)
- RT prices use HB_HUBAVG only (no resource-node prices)
- First week of RTC+B (Dec 5–11) had atypically volatile behavior

## Contact

Issues and contributions:
https://github.com/karthikmattu06-hue/ercot-rtcb-bench/issues
