# Dataset Card: ercot-rtcb-bench v0.1

> Format: [HuggingFace Dataset Card](https://huggingface.co/docs/datasets/dataset_card) /
> [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) (Gebru et al., 2018)

---

## Dataset Summary

`ercot-rtcb-bench` is a versioned, open dataset of post-launch ERCOT market data
for the Real-Time Co-optimization Plus Batteries (RTC+B) market design, which went
live on December 5, 2025. It covers five market observables at 5-minute granularity:
real-time energy prices (LMP), ancillary service (AS) clearing prices for all five
AS products, day-ahead market (DAM) prices, and system conditions (load, wind, solar).

**v0.1** spans December 5, 2025 through March 31, 2026 (117 calendar days post-launch),
with AS clearing data available through March 21, 2026. All timestamps are UTC.

The dataset is designed as the observational foundation for a battery energy storage
bidding benchmark. It does not include bids, positions, or any operator-specific data.
All data is derived from ERCOT's public market data products.

---

## Supported Tasks

- **Battery bidding**: Train and evaluate BESS bidding algorithms on historical market
  data (perfect-foresight MIP, stochastic MILP, reinforcement learning, DFL baselines).
- **Market analysis**: Study post-RTC+B price formation, AS product co-movement,
  and regime changes following the Dec 5, 2025 market design change.
- **Forecasting research**: Benchmark short-horizon energy and AS price forecasters
  against the canonical train/val/test split defined below.

---

## Languages

N/A — the dataset is entirely numeric and tabular (timestamps, prices, quantities).

---

## Dataset Structure

### Tables

All tables are stored as monthly Parquet files in `data/processed/v0.1/<table>/`.

#### `rt_prices/` — 5-minute RT energy prices

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_utc` | datetime[UTC] | — | 5-min interval start, UTC |
| `settlement_point` | str | — | ERCOT settlement point name |
| `settlement_point_type` | str | — | "Trading Hub", "Load Zone", or "Resource Node" |
| `lmp` | float64 | $/MWh | Locational marginal price |
| `is_post_rtcb` | bool | — | Always True in v0.1 |

**v0.1 scope**: HB_HUBAVG only. Additional settlement points planned for v1.0.
**Source**: ERCOT SCED LMP (NP6-788-CD), via gridstatus `ErcotAPI.get_lmp_by_settlement_point`.

#### `as_clearing/` — 5-minute RT ancillary service clearing prices

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_utc` | datetime[UTC] | — | SCED run timestamp (rounded to 5-min), UTC |
| `as_product` | str | — | AS product: REGUP, REGDN, RRS, ECRS, NSPIN |
| `mcpc` | float64 | $/MW | Marginal Clearing Price of Capacity |
| `is_post_rtcb` | bool | — | Always True in v0.1 |

**Note on AS products**: The SCED MCPC data reports five AS products. The RRS
sub-product split (PFR/FFR/UFR) mentioned in ERCOT planning documents is not
reflected in the raw SCED MCPC data product as of March 2026 — RRS appears
as a single product. This schema will be updated if sub-product granularity
becomes available in v1.0.

**Note on coverage**: SCED runs approximately every 5 minutes but not on a
strict clock schedule. After 5-minute binning, ~5% of bins may be empty. The
validation threshold for this table is 94% (vs 99.5% for clock-driven tables).
AS clearing data is available through March 21, 2026 only (see Known Limitations).

**Source**: ERCOT SCED MCPC, pre-downloaded daily Parquet files.

#### `dam_prices/` — hourly DAM prices

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_utc` | datetime[UTC] | — | Hourly interval start, UTC |
| `settlement_point` | str | — | ERCOT settlement point |
| `dam_spp` | float64 | $/MWh | DAM Settlement Point Price |
| `mcpc_regup` | float64 | $/MW | DAM REGUP MCPC |
| `mcpc_regdn` | float64 | $/MW | DAM REGDN MCPC |
| `mcpc_rrs` | float64 | $/MW | DAM RRS MCPC |
| `mcpc_ecrs` | float64 | $/MW | DAM ECRS MCPC |
| `mcpc_nspin_online` | float64 | $/MW | DAM Non-Spin Online MCPC (ADR 0004) |
| `mcpc_nspin_offline` | float64 | $/MW | DAM Non-Spin Offline MCPC (ADR 0004) |
| `is_post_rtcb` | bool | — | Always True in v0.1 |

**Non-Spin split (ADR 0004)**: The DAM distinguishes Non-Spin Online and Offline
as two priced products (NP4-188-CD). RT SCED publishes a single Non-Spin MCPC.
Both DAM codes map to the `nspin` product family via `PRODUCT_FAMILY` in `schema.py`.

**Migration note**: v0.1 Parquet files on disk use legacy `dam_mcpc_*` column names.
The canonical schema (above) uses `mcpc_*`. `smoke_milp.py` handles this rename.

**Source**: gridstatus `Ercot.get_dam_spp` (energy) and `ErcotAPI.get_as_prices` (AS).

#### `asdc_hourly/` — per-hour ASDC breakpoints (added Week 2)

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `operating_date` | date | — | Operating date (Central Time, ERCOT convention) |
| `hour_ending` | int | — | Hour ending 1–24 (Central Time) |
| `as_product` | str | — | AS product: regup, regdn, rrs, ecrs, nspin |
| `segment_index` | int | — | Breakpoint index (0-based) |
| `breakpoint_mw` | float64 | MW | Quantity at this breakpoint |
| `breakpoint_price` | float64 | $/MW-h | ASDC shadow price at this breakpoint |
| `as_plan_mw` | float64 | MW | Published AS plan quantity for this hour |
| `source_filename` | str | — | Source CSV filename within np4-212-cd zip |

**Source**: ERCOT EMILMIS `np4-212-cd` "DAM and SCED Ancillary Service Demand Curves"
(Report Type ID 24893, public, daily). Fetched via `scripts/ingest_asdc_hourly.py`.

#### `asdc_params.parquet` — AORDC mixture-normal parameters (added Week 2)

| Column | Type | Description |
|--------|------|-------------|
| `as_product` | str | AS product (5 values) |
| `effective_date` | date | Effective date for this parameter set |
| `mu`, `sigma` | float64 | Mixture-normal shape parameters (MW) |
| `mix_weight_30min`, `mix_weight_60min` | float64 | Component weights (sum = 1) |
| `voll` | float64 | Value of Lost Load ($/MWh) |
| `voll_cap_offset` | float64 | VOLL cap offset ($/MWh, per NPRR 1268) |
| `min_step_floor` | float64 | ASDC price floor ($/MW-h, per NPRR 1268) |
| `source_url`, `source_doc_revision` | str | Provenance |

**Source**: ERCOT "AORDC Regression Fit Parameters for RTC+B Go-Live" xlsx
(published 2025-09-30, RTCBTF Key Documents page). Parsed via `scripts/ingest_asdc_params.py`.

#### `as_plan/` — AS Plan quantities per operating hour (added Week 3)

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `operating_date` | date | — | Operating date (Central Time, ERCOT convention) |
| `hour_ending` | int | — | Hour ending 1–24 (Central Time) |
| `rureq` | float64 | MW | Regulation-Up reserve requirement |
| `regdnreq` | float64 | MW | Regulation-Down reserve requirement |
| `rrsreq` | float64 | MW | Responsive Reserve Service requirement |
| `ecrsreq` | float64 | MW | ERCOT Contingency Reserve Service requirement |
| `nspinreq` | float64 | MW | Non-Spinning Reserve requirement |

**v0.1 scope**: 117 days × 24 hours = 2,808 expected rows; 2,807 actual (one row
missing for the DST spring-forward non-existent hour, Mar 8 2026 HE 3 CT).

**Source**: ERCOT EMILMIS `np4-33-CD` "DAM Ancillary Service Plan" (Report Type ID 12316,
public, daily). Two-surface ingest per ADR 0005: MISAPP for recent data
(`data/as_plan.py: fetch_as_plan_current`), ERCOT Public Data API archive for
historical backfill (`scripts/backfill_as_plan_history.py`).

**Consumer**: Required as an input to the NPRR1268 per-product ASDC disaggregation
formula (see Chunk 3 / ADR 0006).

#### `system_conditions/` — 5-minute system-level observables

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_utc` | datetime[UTC] | — | 5-min interval start, UTC |
| `total_load_mw` | float64 | MW | ERCOT system-wide actual load |
| `load_forecast_mw` | float64 | MW | ERCOT load forecast |
| `wind_actual_mw` | float64 | MW | Wind actual generation |
| `wind_forecast_mw` | float64 | MW | Short-term wind power forecast (STWPF) |
| `solar_actual_mw` | float64 | MW | Solar actual generation |
| `solar_forecast_mw` | float64 | MW | Short-term solar forecast (STPPF) |
| `net_load_mw` | float64 | MW | total_load − wind_actual − solar_actual |
| `is_post_rtcb` | bool | — | Always True in v0.1 |

**Source**: gridstatus `ErcotAPI.get_wind_actual_and_forecast_hourly`,
`ErcotAPI.get_load_forecast_by_model`, `Ercot.get_hourly_load_post_settlements`.

---

## Data Splits

The following canonical train/val/test split is defined for benchmark use.
**Do not tune hyperparameters on the test set.**

| Split | Start | End | Days | Notes |
|-------|-------|-----|------|-------|
| **Train** | 2025-12-05 06:00 UTC | 2026-02-14 06:00 UTC | 71 | Post-launch learning period |
| **Val** | 2026-02-14 06:00 UTC | 2026-03-01 06:00 UTC | 15 | Hyperparameter selection |
| **Test** | 2026-03-01 06:00 UTC | 2026-03-31 23:55 UTC | 31 | Held-out evaluation |

**Rationale**: 71/15/31 day split gives reasonable training data while keeping
a contiguous 31-day test period. The train/val boundary is mid-February to avoid
the val set being dominated by early-market learning effects (first two months).
All splits are chronological; no random shuffling. The val set spans one ERCOT
seasonal billing cycle.

**v1.0 note**: The v1.0 split will extend test to June 5, 2026, covering spring
conditions. The train boundary will remain Dec 5, 2025.

---

## Data Source

All data is derived from ERCOT public data products:

| Product | ERCOT endpoint / NPRR | gridstatus method | Granularity |
|---------|----------------------|-------------------|-------------|
| RT LMP | NP6-788-CD (SCED LMP) | `ErcotAPI.get_lmp_by_settlement_point` | 5-min |
| SCED MCPC | SCED MCPC file (public portal) | Pre-downloaded | ~5-min |
| DAM SPP | DAM SPP report | `Ercot.get_dam_spp` | Hourly |
| DAM AS prices | DAM AS clearing | `ErcotAPI.get_as_prices` | Hourly |
| Load actual | ERCOT hourly load | `Ercot.get_hourly_load_post_settlements` | Hourly |
| Load forecast | ERCOT short-term load forecast | `ErcotAPI.get_load_forecast_by_model` | Hourly |
| Wind/solar | STWPF/STPPF | `ErcotAPI.get_wind_actual_and_forecast_hourly` | Hourly |

API endpoint: `ercotapi.app.ercot.com` (public ERCOT API, requires registration).

---

## Annotations

None. This is observational market data; no manual annotation was performed.

---

## Personal / Sensitive Information

None. All data is aggregate market-level data published by ERCOT. No individual
operator positions, bids, or personally identifiable information is included.

---

## Curation Rationale

**Why post-RTC+B only?** RTC+B represents a structural break in the market microstructure.
Pre-launch data has fundamentally different action spaces, pricing logic, and AS product
definitions. Training on pre-launch data and evaluating on post-launch data would
conflate regime change with algorithm performance. v0.1 is purely post-launch.

**Why this settlement point scope?** v0.1 uses HB_HUBAVG as the single settlement
point, which is the hub average price commonly used as the reference price for
BESS dispatch in ERCOT. HB_HUBAVG is available in the historical LMP data going
back to 2020, making it the most reliable starting point. Additional settlement
points will be added in v1.0 once the fetch infrastructure for multi-SP LMP is
validated.

**Why these AS products?** The five products (REGUP, REGDN, RRS, ECRS, NSPIN)
represent all ancillary services for which ERCOT publishes RT SCED clearing prices.
This is the complete observable AS action space for a BESS under RTC+B.

---

## Known Limitations

1. **Single settlement point**: v0.1 RT prices are HB_HUBAVG only. Real BESS
   resources may settle at load zone or resource node prices that diverge from
   the hub, especially during congestion events.

2. **AS clearing coverage through March 21 only**: The raw SCED MCPC data product
   available to us extends through March 21, 2026. The last 10 days of March have
   RT energy, DAM, and system condition data but no AS clearing prices. v1.0 will
   close this gap via a re-fetch.

3. **RRS sub-product granularity**: ERCOT planning documents describe PFR/FFR/UFR
   sub-products within RRS. As of March 2026, the SCED MCPC data reports a single
   RRS price. If sub-product data becomes available, the schema and benchmark will
   be updated.

4. **Non-Spin online vs offline**: The RT SCED MCPC product reports a single NSPIN
   MCPC. The DAM distinguishes online and offline Non-Spin; this distinction is not
   yet captured in the RT table.

5. **Early-market transient effects (Dec 5–11, 2025)**: The first week of RTC+B
   had atypically volatile prices and AS clearing behavior as operators and ERCOT
   calibrated to the new market design. Models trained on this period may overfit
   to launch-day anomalies.

6. **MIP optimality gap regime change (Jan 8, 2026)**: ERCOT tightened the SCED
   co-optimization MIP gap from ~2% to ~0.5% on January 8, 2026. This creates a
   subtle distributional shift mid-dataset. The `is_post_mip_tighten` flag in
   `rtcb.py` marks this boundary.

7. **Small negative MCPC values**: Three REGDN intervals on December 30-31 have
   MCPC values of -$0.01 (rounding artifact from the pricing engine). These are
   treated as effectively zero and do not fail validation (tolerance = -$0.05/MW).

---

## Baselines

The repository ships two LP baselines (Week 2 addition):

| Baseline | Module | Description |
|----------|--------|-------------|
| **Perfect foresight** | `methods/perfect_foresight.py` | Knows all future RT prices exactly; upper bound on achievable revenue |
| **Point forecast** | `methods/point_forecast.py` | Optimizes with DAM prices as forecast; settles at RT prices |

**Feb 1–7, 2026 smoke run** (100 MW / 400 MWh BESS at HB_HUBAVG, Gurobi 13):

| Baseline | Revenue (7 days) | Capture |
|----------|-----------------|---------|
| Perfect foresight | $178,442 | 100% (upper bound) |
| Point forecast (DAM) | $136,100 | 76.3% |

Run with: `python scripts/smoke_milp.py --v01-dir path/to/v0.1`

---

## License

**Data**: Derived from ERCOT public data products. Users are responsible for
compliance with ERCOT's data terms of use, available at ercot.com. ERCOT
publishes its market data under a terms of service that permits academic
and commercial use of public market data without fee.

**Code** (transform, validation, benchmark scripts): Apache-2.0
(see `LICENSE` file in this repository).

---

## Citation

```bibtex
@software{mattu2026ercotrtcbbench,
  author = {Mattu, Karthik},
  title  = {ercot-rtcb-bench: An Open Benchmark for Battery Bidding in Post-RTC+B ERCOT},
  year   = {2026},
  url    = {https://github.com/karthikmattu06-hue/ercot-rtcb-bench},
}
```

See also `CITATION.cff` in the repository root.

---

## Versions

| Version | Date range | Released | Notes |
|---------|------------|----------|-------|
| **v0.1** | 2025-12-05 – 2026-03-31 | 2026-05 | This release. AS clearing through Mar 21 only. |
| **v1.0** | 2025-12-05 – 2026-06-05 | Planned | Full 6-month window. ASDC parameters. Multi-SP LMP. |

See `docs/decisions/0001-versioned-datasets.md` for the rationale behind the
v0.1 / v1.0 release strategy.
