# W4-A Results: Realized-Gap Attribution

**Panel:** Apr 20–26, 2026 (168 hours)  
**BESS:** 100 MW / 400 MWh, RTE=0.88  
**Solver:** Gurobi (license renewed)  
**Canonical seed:** 42 (per-day independent RNG, ADR 0007)

---

## Phase 1 — Per-HoD LMP Bias

| HoD (UTC) | Forecast | Realized | Bias ($/MWh) |
|---:|---:|---:|---:|
| 0 | $83.57 | $132.34 | **−$48.77** |
| 1 | $79.46 | $126.71 | **−$47.25** |
| 2 | $85.96 | $67.03 | +$18.93 |
| 3 | $57.03 | $51.88 | +$5.15 |
| 4 | $27.42 | $28.27 | −$0.85 |
| 5 | $20.99 | $27.14 | −$6.15 |
| 6 | $23.66 | $25.34 | −$1.69 |
| 7 | $21.17 | $25.15 | −$3.98 |
| 8 | $22.77 | $26.08 | −$3.31 |
| 9 | $24.31 | $29.03 | −$4.72 |
| 10 | $33.26 | $33.78 | −$0.53 |
| 11 | $31.47 | $35.21 | −$3.74 |
| 12 | $30.91 | $32.33 | −$1.42 |
| 13 | $32.86 | $43.44 | −$10.59 |
| 14 | $20.56 | $31.13 | −$10.57 |
| 15 | $22.28 | $28.78 | −$6.50 |
| 16 | $16.86 | $26.24 | −$9.38 |
| 17 | $20.07 | $23.91 | −$3.84 |
| 18 | $22.44 | $27.09 | −$4.65 |
| 19 | $22.85 | $31.32 | −$8.47 |
| 20 | $30.95 | $34.23 | −$3.28 |
| 21 | $31.19 | $36.56 | −$5.37 |
| 22 | $35.75 | $34.79 | +$0.96 |
| 23 | $57.73 | $60.66 | −$2.93 |

**Overall mean bias: −6.79 $/MWh**

**Verdict: Peak-concentrated, not uniform.** HoD 0 and 1 UTC (7–8 pm CDT, the evening peak) dominate, with −$48.77 and −$47.25 $/MWh underestimation. All other hours are mild (−1 to −11 $/MWh), with slight overestimation at HoD 2–3 (post-peak reversion).

---

## Phase 2 — Oracle Counterfactuals

### 2×2 Attribution Table

| Variant | Revenue | vs Baseline | vs EV | vs PF |
|---|---:|---:|---:|---:|
| **Baseline** (Stochastic LP) | **$238,376** | — | −$11,797 | −$113,236 |
| CF-A: Oracle LMP | $259,855 | +$21,479 | +$9,682 | −$91,757 |
| CF-B: Oracle AS | $275,458 | +$37,082 | +$25,284 | −$76,154 |
| CF-AB: Oracle LMP + AS | $296,068 | +$57,691 | +$45,894 | −$55,544 |
| EV-det LP (comparator) | $250,174 | +$11,797 | — | −$101,438 |
| PF LP (upper bound) | $351,612 | +$113,236 | +$101,438 | — |

### Gain Decomposition

| Term | Amount | % of CF-AB total |
|---|---:|---:|
| ΔLMP | +$21,479 | 37.2% |
| ΔAS | +$37,082 | 64.3% |
| Interaction | −$870 | −1.5% |
| **CF-AB total** | **+$57,691** | **100%** |

**Residual-to-PF (CF-AB → PF): −$55,544** (irreducible uncertainty in future price paths)

---

## Interpretation

### Why both sources individually exceed the gap

The −$11,797 gap is smaller than ΔLMP (+$21,479) and ΔAS (+$37,082) independently. This is not a paradox — it reflects that in the baseline the two bias sources partially cancel:

- Scenarios underestimate LMP → LP under-dispatches energy, holding SoC → foregone energy revenue
- Scenarios underestimate AS → LP under-commits AS, dispatching more energy → partially offsets the LMP error

Correcting either error alone removes a constraint on the LP without compensating for the other, recovering more than the observed gap.

### AS bias is the dominant error source

ΔAS ($37,082) is 1.73× ΔLMP ($21,479). The AS under-coverage finding from W3-B (51–56% vs 80% target) has a larger revenue impact than LMP mean underestimation. This is somewhat counterintuitive given the large HoD 0–1 LMP spike, but reflects that the stochastic LP can partly hedge LMP uncertainty through energy dispatch timing even with biased scenarios, while AS commitment has less flexibility.

### Oracle LMP alone beats EV

CF-A ($259,855) > EV ($250,174) by +$9,682. This confirms: the stochastic LP's structural advantage is intact; what is failing is forecast quality. With unbiased LMP scenarios, stochastic would have outperformed EV on this panel.

### Interaction is near-zero

Interaction = −$870 (−1.5% of total). LMP and AS corrections are nearly independent. The two oracle corrections address distinct LP decision margins (energy dispatch vs AS commitment), so their effects add almost linearly.

### Residual to PF

Even with both oracle corrections ($296,068), the LP leaves $55,544 on the table vs PF ($351,612). This residual represents genuine price-path uncertainty: the stochastic LP commits stage-1 decisions under uncertainty, while PF uses future RT prices directly.

---

## Engineering Notes

- **Oracle construction:** Per-hour additive shift of scenario means to realized RT means. Dispersion preserved (CF-A). AS clipped ≥ 0 after shift (CF-B). Applied to full 288-interval day arrays before LP runs — not just the committed 12-interval window.
- **Baseline reproduction:** $238,376.27 — exact match to W3-C audit (cent-for-cent).
- **CF-B scope:** Mean bias correction only. Dispersion scaling to achieve 80% AS interval coverage is out of scope for W4-A (deferred to W4-B).
- **Runtime:** ~177s for all 4 variants (168 hours each, Gurobi, ~0.24s/solve).
