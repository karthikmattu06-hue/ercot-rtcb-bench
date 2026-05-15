# v0.1 Coverage Notes

**Generated:** 2026-05-15  
**Window:** 2025-12-05 (RTC+B launch) – 2026-03-31  
**Calendar days:** 117

## Row counts

| Table | Location | Files | Rows |
|-------|----------|-------|------|
| `rt_prices` | `~/hybridbid-bench-data/v0.1/rt_prices/` | 4 monthly | 33,624 |
| `as_clearing` | `~/hybridbid-bench-data/v0.1/as_clearing/` | 4 monthly | 152,260 |
| `dam_prices` | `~/hybridbid-bench-data/v0.1/dam_prices/` | 4 monthly | 2,796 |
| `system_conditions` | `~/hybridbid-bench-data/v0.1/system_conditions/` | 4 monthly | 33,624 |
| `asdc_hourly` | `~/hybridbid-bench-data/v0.1/asdc_hourly/` | 117 daily | 21,650,559 |
| `as_plan` | `data/processed/v0.1/as_plan/` | 4 monthly | 2,807 |
| `asdc_params` | `data/processed/v0.1/asdc_params.parquet` | 1 static | 5 |

## Oracle validation sample count (114 vs 117 days)

The oracle validation script initially reported 114 sampled days rather than 117.
Investigation revealed two script-default bugs — not data gaps:

1. **Start date was Dec 1, not Dec 5.** Dec 1–4 predate the RTC+B market launch;
   neither AS Plan nor ASDC oracle data exists for those dates. They silently
   inflated the "skipped" counter by 4.
2. **End date was Mar 28, not Mar 31.** Three valid days (Mar 29–31) were simply
   excluded by the wrong default. All three have complete oracle and AS Plan data.

After correcting the defaults to `2025-12-05 – 2026-03-31`, the oracle validation
runs 117/117 days with 0 skipped for all four upward products.

## DST

Spring-forward occurs on **2026-03-08** (HE 3 does not exist). The AS Plan table
has 2,807 rows rather than `117 × 24 = 2,808` because that one HE is absent. This
is expected behavior, not a gap.

## AS clearing coverage

Per Known Limitation #2 in the dataset card, the raw SCED MCPC data extends
through **March 21, 2026** only. The last 10 days of March (Mar 22–31) have
RT energy, DAM, and system condition data but no AS clearing prices. This gap
affects `as_clearing` row counts but not the oracle validation (which uses
`asdc_hourly` + `as_plan`, both fully present through Mar 31).
