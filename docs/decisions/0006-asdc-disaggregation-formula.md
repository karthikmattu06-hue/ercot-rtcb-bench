# ADR 0006 — NPRR1268 §4.4.12 ASDC Disaggregation Formula

**Status:** Accepted (2026-05-15)

**Context.** The `asdc_hourly` oracle tables give us the published, per-product ASDC
breakpoints for every (operating_date, hour_ending, product) tuple. However, the source
of truth for *how* ERCOT constructs those breakpoints from the aggregate AORDC curve
and the AS Plan is §4.4.12(7)(b) of the NPRR1268 PUCT Report (May 2025). Implementing
this formula correctly is the prerequisite for running oracle validation over the full
v0.1 window and for generating the ASDC inputs required by the bidding agent.

**Decision.** Implement the NPRR1268 §4.4.12(7)(b) disaggregation algorithm exactly
as written in the PUCT Report. The algorithm:

1. **MCL allocation** (`_mcl_quantities`): Allocate 3,000 MW MCL across four upward
   products (RegUp, RRS, ECRS, NSPIN) using the three-case formula with fixed constants
   RUPCT=0.90, RRSPCTMAX=0.90, ECRSPCTMAX=0.30, ECRSMWMIN=40, NSMWMIN=10. All
   allocated quantities are rounded to the nearest integer MW.

2. **AORDC discretization** (`_aordc_discretized`): Evaluate `AORDC(R) = (1 −
   Φ((R − MCL − μ)/σ)) × VOLL` at every integer reserve level from 3000 to 10702
   (7703 points), keeping only levels where AORDC > $0.01. Published parameters:
   μ=675, σ=1524, VOLL=5000.

3. **RegUp sampling** (step i): Draw `n_regup = rureq − rumw` reserve levels
   evenly from the pool `{R : R ≤ k_regup}` using `round(linspace(0, pool_size−1, n))`.
   Here `k_regup` is the last reserve level with AORDC ≥ $250.

4. **RRS sampling** (step ii): Draw `n_rrs = rrsreq − rrsmw` reserve levels evenly
   from the pool `{R : R ≤ k_rrs and R ∉ RegUp_set}` using the same linspace-index
   approach. The pool exclusion prevents RegUp/RRS overlap by construction.

5. **ECRS/NSPIN alternating** (steps iii–iv): From the remaining reserves
   (all AORDC levels not drawn by RegUp or RRS, sorted ascending), ECRS takes the
   even-indexed elements until `n_ecrs = ecrsreq − ecrsmw` are filled. NSPIN takes
   the interleaved odd-indexed elements plus *all remaining* reserves beyond the ECRS
   fill depth. NSPIN's breakpoint curve therefore extends beyond `nspinreq`.

6. **Curve assembly**: Each product curve has two MCL breakpoints at
   `(0, max_demand_price)` and `(mcl_mw, max_demand_price)`, followed by N nonlinear
   breakpoints at `(mcl_mw + j + 1, AORDC(R_j))` for j = 0..N−1. Max demand prices
   per product: RegUp=9052, RRS=7051, ECRS=5050, NSPIN=5000 $/MW-h.

7. **$15/MW-h floor** (NPRR1269): Applied to all upward products. For NSPIN, the
   floor applies only for breakpoints within `nspinreq`; the extension beyond that
   threshold uses raw AORDC.

**Validation.** Oracle reconstruction was evaluated against 114 operating days
(2025-12-01 through 2026-03-28, HE13) for four upward products. 4 days had no oracle
data and were skipped. Results:

| Product | n days | Mean price error | Max mean error | Status |
|---------|--------|-----------------|----------------|--------|
| RegUp   | 114    | $0.0176/MW-h    | $0.0257/MW-h   | PASS   |
| RRS     | 114    | $0.0046/MW-h    | $0.0116/MW-h   | PASS   |
| ECRS    | 114    | $0.0024/MW-h    | $0.0025/MW-h   | PASS   |
| NSPIN   | 114    | $0.0022/MW-h    | $0.0029/MW-h   | PASS   |

Acceptance criterion: mean price error ≤ $0.10/MW-h per product. All four pass by
more than 3×. MW breakpoint errors are identically zero (integer-MW curves).

**Consequences.**
- `reconstruct_per_product_asdc()` in `data/asdc.py` is the canonical formula
  implementation. Tests in `test_asdc_oracle.py` cover both unit formula invariants
  and a single-hour integration test against oracle data.
- The oracle data in `~/hybridbid-bench-data/v0.1/asdc_hourly/` is derived from the
  ERCOT np4-212-CD reports and is treated as ground truth.
- GitHub issue #1 is closed by this validation.
- For v1.0, re-run the validation window over the extended date range and confirm
  mean error remains ≤ $0.10/MW-h per product.
