# W3-B Backtest Report: Bootstrap Probabilistic Forecaster

**Gate status:** ✗ FAILED

## Gate Issues
- [Apr 20-26 2026 (primary)] lmp: |bias|=6.789 exceeds threshold 5.0
- [Apr 20-26 2026 (primary)] mcpc_regup: 80% coverage=55.3% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_regdn: 80% coverage=51.3% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_rrs: |bias|=1.376 exceeds threshold 0.5
- [Apr 20-26 2026 (primary)] mcpc_rrs: 80% coverage=55.6% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_ecrs: |bias|=1.098 exceeds threshold 0.5
- [Apr 20-26 2026 (primary)] mcpc_ecrs: 80% coverage=51.5% < 60% threshold
- [Apr 20-26 2026 (primary)] mcpc_nspin: 80% coverage=48.0% < 60% threshold

## Panel: Apr 20-26 2026 (primary)
Days: 2026-04-20, 2026-04-21, 2026-04-22, 2026-04-23, 2026-04-24, 2026-04-25, 2026-04-26

### Per-Series Metrics (averaged over panel)

| Series | Mean Bias | Std Bias | Mean CRPS | 80% Coverage | N Days |
|--------|-----------|----------|-----------|--------------|--------|
| lmp | -6.789 $/MWh | 13.698 | 20.107 | 86.6% | 7 |
| mcpc_regup | +0.900 $/MW | 4.140 | 3.440 | 55.3% | 7 |
| mcpc_regdn | +0.773 $/MW | 1.222 | 1.281 | 51.3% | 7 |
| mcpc_rrs | +1.376 $/MW | 3.936 | 3.286 | 55.6% | 7 |
| mcpc_ecrs | +1.098 $/MW | 4.391 | 4.068 | 51.5% | 7 |
| mcpc_nspin | +0.766 $/MW | 9.455 | 8.720 | 48.0% | 7 |

### Per-Day Details

- **2026-04-20**: K=15, pool=101, matched=40, relaxed=False
- **2026-04-21**: K=15, pool=102, matched=40, relaxed=False
- **2026-04-22**: K=15, pool=103, matched=40, relaxed=False
- **2026-04-23**: K=15, pool=104, matched=40, relaxed=False
- **2026-04-24**: K=15, pool=105, matched=40, relaxed=False
- **2026-04-25**: K=15, pool=106, matched=30, relaxed=False
- **2026-04-26**: K=15, pool=107, matched=31, relaxed=False
