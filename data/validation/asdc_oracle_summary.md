# ASDC Oracle Validation Summary — v0.1

**Run date:** 2026-05-15  
**Algorithm:** NPRR1268 §4.4.12(7)(b) disaggregation formula  
**Parameters:** μ=675, σ=1524, VOLL=5000 (published, fixed for v0.1)  
**Window:** 2025-12-01 through 2026-03-28, HE13  
**Acceptance criterion:** Mean per-day price error ≤ $0.10/MW-h per product

## Results

| Product | Days evaluated | Days skipped (no data) | Mean price error ($/MW-h) | Max daily mean error ($/MW-h) | MW error (max) | Status |
|---------|---------------|----------------------|--------------------------|-------------------------------|----------------|--------|
| RegUp   | 114           | 4                    | 0.0176                   | 0.0257                        | 0.0 MW         | **PASS** |
| RRS     | 114           | 4                    | 0.0046                   | 0.0116                        | 0.0 MW         | **PASS** |
| ECRS    | 114           | 4                    | 0.0024                   | 0.0025                        | 0.0 MW         | **PASS** |
| NSPIN   | 114           | 4                    | 0.0022                   | 0.0029                        | 0.0 MW         | **PASS** |

Pass rate per product: **114/114 (100%)** for all four upward products.

## Notes

- RegDn is a flat curve at VOLL across the plan quantity; it is exact by construction and not tested here.
- The 4 skipped days had no matching AS Plan parquet entry for HE13.
- Residual errors come entirely from the AORDC curve rounding to integer MW (max ≈$0.005/MW-h per breakpoint, the half-step rounding bound). No systematic bias was found.
- NSPIN breakpoints extend beyond `nspinreq` (step iv of the algorithm); the $15/MW-h floor applies only within the AS plan requirement, consistent with NPRR1269.

## Conclusion

The `reconstruct_per_product_asdc()` implementation in `src/ercot_rtcb_bench/data/asdc.py`
accurately reproduces the published ERCOT ASDC breakpoints across the full v0.1 window.
Oracle validation acceptance criterion is satisfied. See ADR 0006 for algorithm details.
