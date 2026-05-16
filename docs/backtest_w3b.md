# W3-B Backtest Report: Bootstrap Probabilistic Forecaster

**Gate status:** ✗ FAILED

## Gate Issues
- [Apr 20-26 2026 (primary)] lmp: |bias|=12.552 exceeds threshold 5.0
- [Apr 20-26 2026 (primary)] mcpc_regup: 80% coverage=55.5% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_regdn: 80% coverage=48.9% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_rrs: |bias|=1.343 exceeds threshold 0.5
- [Apr 20-26 2026 (primary)] mcpc_rrs: 80% coverage=52.8% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_ecrs: |bias|=1.016 exceeds threshold 0.5
- [Apr 20-26 2026 (primary)] mcpc_ecrs: 80% coverage=52.7% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_nspin: 80% coverage=47.2% < 60% threshold

## Panel: Apr 20-26 2026 (primary)
Days: 2026-04-20, 2026-04-21, 2026-04-22, 2026-04-23, 2026-04-24, 2026-04-25, 2026-04-26

### Per-Series Metrics (averaged over panel)

| Series | Mean Bias | Std Bias | Mean CRPS | 80% Coverage | N Days |
|--------|-----------|----------|-----------|--------------|--------|
| lmp | -12.552 $/MWh | 13.180 | 13.500 | 60.2% | 7 |
| mcpc_regup | +0.860 $/MW | 4.130 | 3.455 | 55.5% | 7 |
| mcpc_regdn | +0.891 $/MW | 1.352 | 1.287 | 48.9% | 7 |
| mcpc_rrs | +1.343 $/MW | 3.918 | 3.281 | 52.8% | 7 |
| mcpc_ecrs | +1.016 $/MW | 4.389 | 4.007 | 52.7% | 7 |
| mcpc_nspin | +0.795 $/MW | 9.498 | 8.928 | 47.2% | 7 |

### Per-Day Details

- **2026-04-20**: K=15, pool=101, matched=40, relaxed=False
- **2026-04-21**: K=15, pool=102, matched=40, relaxed=False
- **2026-04-22**: K=15, pool=103, matched=40, relaxed=False
- **2026-04-23**: K=15, pool=104, matched=40, relaxed=False
- **2026-04-24**: K=15, pool=105, matched=40, relaxed=False
- **2026-04-25**: K=15, pool=106, matched=30, relaxed=False
- **2026-04-26**: K=15, pool=107, matched=31, relaxed=False
