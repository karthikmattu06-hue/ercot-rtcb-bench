# Blog #2 Facts Pack — source-pinned figures

**Purpose:** every number blog #2 may cite, each with the committed artifact it comes from.
**Discipline:** read-only extraction from committed artifacts — **no recomputation**. Any
figure not found in a committed artifact is listed under **§8 NOT FOUND — do not cite**.
Format per entry: **value · what it is · source (file + field, or ADR §)**.

Cross-cutting note on the eval baseline: two values are canonical depending on data
vintage. **$238,376.27** is the pre-rebuild baseline (W3-C/W4/W5-A ran on it);
**$238,378.80** is the ADR 0013 re-pinned baseline (canonical forward, +$2.53, AS-only).
Both are cited below with their sources.

---

## 1. Benchmark anchors (re-pinned canonical, ADR 0013 forward)

| Value | What it is | Source |
|---|---|---|
| **$238,378.80** | Stochastic LP eval baseline, re-pinned canonical | ADR 0013 §Decision.2; `data/audit/w5r_run.json` → `eval_baseline_repinned` (238378.8) |
| **$238,376.27** | Stochastic LP eval baseline, pre-rebuild (superseded) | ADR 0013 §Context; `data/audit/w5a_eval.json` → `phase3.baseline.revenue_total` (238376.27192) |
| Supersedes note | "+$2.53 (0.001%), AS-only, changes no qualitative finding, parameter, or ordering" | ADR 0013 §Decision.3 |
| **Apr 20–26, 2026** | Eval panel definition (7 days, 168 hours) | `docs/results_w3d.md` (Panel header); ADR 0010 §Phase 2; `data/audit/backtest_w4b.json` → `panel_start`/`panel_end` (2026-04-20 → 2026-04-27) |

### Five-method eval-panel table (Apr 20–26)
Source: `docs/results_w3d.md` §Five-Method Comparison (DFL row also `data/audit/backtest_w3d_eval.json`).
Solver at the time: scipy HiGHS (Gurobi license lapse noted in that doc). Totals in $.

| Method | Total | Energy | AS | Term.Liq | vs PF |
|---|---:|---:|---:|---:|---:|
| PF LP (upper bound) | 351,612 | 253,765 | 97,601 | 245 | 100.0% |
| Deterministic LP — DAM | 238,421 | 185,034 | 47,871 | 5,516 | 67.8% |
| Deterministic LP — EV (scenario mean) | 250,174 | 168,703 | 73,412 | 8,058 | 71.2% |
| Stochastic LP — scenario tree | 238,376 | 159,021 | 72,478 | 6,878 | 67.8% |
| DFL-MLP → Deterministic LP | 236,591 | 183,289 | 47,899 | 5,403 | 67.3% |

- DFL vs DAM-det: **−$1,830** (−0.8%); DFL vs EV-det: **−$13,583** (−5.4%) — `data/audit/backtest_w3d_eval.json` → `dfl_vs_dam_usd`, `dfl_vs_ev_usd`; `docs/results_w3d.md`.
- The Stochastic-LP row (238,376) is pre-repin; re-pinned value is 238,378.80 (§1 row 1).

---

## 2. W4 decomposition of the Stochastic→PF headroom

**Headroom (Stochastic → PF) = $113,236** — ADR 0010 §Phase 2; `docs/results_w4a.md` (PF $351,612 vs baseline $238,376).

### Level 1 — ADR 0010 identity (source of the $36,393 AS bound)
Source: **ADR 0010 §Phase 2 "Decomposition of the $113,236 Stochastic→PF headroom"**.

| Leg | Amount | Share |
|---|---:|---:|
| ΔLMP (LMP mean bias) | **+$21,479** | 19.0% |
| ΔAS (AS effective-price error) | **+$36,393** | 32.1% |
| Interaction | **−$2,194** | −1.9% |
| Residual | **+$57,558** | 50.8% |
| **Total** | **$113,236** | 100.0% |

Identity (verbatim, ADR 0010 line 126): `$21,479 + $36,393 − $2,194 + $57,558 = $113,236 ✓`.
Oracle-variant revenues: CF-A (oracle LMP) $259,855; CF-B (E[max] AS oracle) $274,770;
CF-AB $294,054; PF $351,612 — ADR 0010 §Phase 2 table.

### Level 2 — ADR 0011 / W4-B decomposition of the $57,558 residual
Source: **ADR 0011 §** table; `data/audit/backtest_w4b.json` → `decomposition.*`.

| Leg | Amount | Share | Source field |
|---|---:|---:|---|
| ΔLMPdisp (calibration) | **+$5,866** | 10.2% | `decomposition.delta_lmpdisp` (5866.449) |
| ΔASdisp (calibration) | **+$244** | 0.4% | `decomposition.delta_asdisp` (243.929) |
| Interaction | **−$157** | −0.3% | `decomposition.interaction2` (−157.411) |
| Remainder | **+$51,605** | 89.7% | `decomposition.remainder` (51604.674) |
| **Total** | **$57,558** | 100.0% | `decomposition.identity_check` (57557.64) |

- **Formulation gap G = $14** (bracket [$14, $4,467]) — ADR 0011 line 122/144; `docs/results_w4b.md` (remainder $51,605 ≳ G $14).
- **Bracket [calibration lower, perfect-path upper]** — ADR 0011 lines 115–116; `data/audit/backtest_w4b.json` → `bracket.lmp`/`bracket.as`:
  - LMP: **[+$5,866, +$56,713]**
  - AS: **[+$244, +$3,347]**
- Perfect-path runs: U_LMP $350,768; U_AS $297,401; **U_both $353,016.61 ≡ unclamped R_struct** — `docs/results_w4b.md`; `backtest_w4b.json` → `runs.u_lmp/u_as/u_both.revenue_total`.

> ⚠️ Provenance variance (see §8): `docs/results_w4a.md` reports the AS oracle leg as
> **+$37,082** (CF-B $275,458, interaction −$870); **ADR 0010** reports **+$36,393**
> (CF-B $274,770, interaction −$2,194). The **$36,393** value is the one carried forward
> (W5-A `oracle_bound`, ADR 0012). Cite ADR 0010's $36,393 for the headroom identity.

---

## 3. W5-A — scarcity-conditioned DAM AS anchor shrinkage (ADR 0012)

### Fitted parameters (τ_p, s_p), all four corrected products
Source: `data/audit/w5a_eval.json` → `phase2.fit`. (RegUp/RRS/ECRS/NSpin; RegDn and LMP untouched.)

| Product | τ_p | s_p | note |
|---|---:|---:|---|
| regup | 3.56 | 0.15195465087890625 | ok |
| rrs | 2.71 (τ_hourly 2.707) | 0.00125885009765625 | ok |
| ecrs | 2.56 (τ_hourly 2.557) | 0.0374603271484375 | ok |
| nspin | 14.98 | 0.0 | **clamped_zero** (anchor over-quote even at floor; ADR 0012 open thread) |

- **RegDn-flat finding:** RegDn is **not corrected** — smallest bias, near-unity ratio
  (bias_eff **+0.23**, ratio_eff **1.21×**, mean F 1.36 / realized 1.13) — `docs/results_w5a_diagnostic.md` §Overall bias table.

### Phase-1 diagnostic — over-forecast on every product (train Jan 23–Apr 13)
Source: `docs/results_w5a_diagnostic.md` §Phase 1 (backing raw: `data/audit/w5a_diagnostic.json` → `phase1.train`).

| Product | bias_eff | bias_dam | ratio_eff | mean F_eff | mean realized | top-decile share |
|---|---:|---:|---:|---:|---:|---:|
| regup | +1.90 | +2.12 | 2.24× | 3.44 | 1.54 | 98.6% |
| regdn | +0.23 | +0.19 | 1.21× | 1.36 | 1.13 | 96.6% |
| rrs | +2.53 | +2.85 | 5.62× | 3.07 | 0.55 | 99.8% |
| ecrs | +2.51 | +2.62 | 4.39× | 3.26 | 0.74 | 99.9% |
| nspin | +3.32 | +3.86 | 2.53× | 5.48 | 2.16 | 99.7% |

Scarcity-quartile bias_eff (realized-LMP Q4, high) — `docs/results_w5a_diagnostic.md` §"Bias by realized-LMP quartile":
regup **+6.62** · regdn +0.03 · rrs **+8.80** · ecrs **+9.27** · nspin **+8.61** (Q1–Q3 all mild, +0.0 to +2.6).

### Phase-3 eval (Apr 20–26)
Source: `data/audit/w5a_eval.json` → `phase3.*`; ADR 0012.

| Value | What it is | Field |
|---|---|---|
| **+$18,271** | ΔW5A eval gain (correction on vs off) | `phase3.delta_w5a` (18271.390) |
| **50.2%** | recovery of the $36,393 oracle bound | `phase3.recovery_fraction` (0.502058); ADR 0012 line 79 |
| $36,393 | oracle bound (W4-A ΔAS) | `phase3.oracle_bound` (36393.0) |
| +$13,495 / +$3,947 / +$829 | component deltas E / AS / Liq | `phase3.delta_energy` / `delta_as` / `delta_liq` |
| **Apr 25 +$18,694** | biggest single-day gain (the scarcity day) | `phase3.per_day_delta["2026-04-25"]` (18694.065) |
| **Apr 24 −$5,524** | worst loss day | `phase3.per_day_delta["2026-04-24"]` (−5524.100) |
| **Apr 22 −$1,155** | second loss day | `phase3.per_day_delta["2026-04-22"]` (−1154.978) |
| ≈ $18.1k | bound − realized, unattributed | ADR 0012 line 134 |

---

## 4. W5-R — out-of-sample replication, frozen params (ADR 0014)

### Cross-panel table
Source: `data/audit/w5r_run.json` → `synthesis` / `panels`. Δ = corrected − baseline; both-up = E&AS both rise.

| Panel | Baseline | Δ total | Δ / PF-headroom | worst day (Δ) | E&AS both up? |
|---|---:|---:|---:|---|:--:|
| Apr 20–26 (eval, restated) | 238,378.80 | **+$18,270** | +16.2% | 2026-04-24 (−$5,524) | yes |
| Apr 27–May 3 (scarcity, confirmatory) | 321,419.73 | **+$6,303** | +6.8% | 2026-04-27 (−$15,025) | yes |
| Jun 1–7 (scarcity, primary) | 87,532.86 | **−$4,765** | −4.6% | 2026-06-04 (−$8,755) | no |
| May 4–10 (calm) | 60,388.34 | **−$10,619** | −18.8% | 2026-05-05 (−$7,514) | no |

- **Verdict (verbatim):** "ONE scarcity panel positive — lever real but high-variance; no v0.2 claim without more panels" — `data/audit/w5r_run.json` → `verdict`.
- Frozen params asserted == ADR 0012 (no refit) — `w5r_run.json` → `frozen_params` (regup τ3.56/s0.15195, rrs τ2.71/s0.00126, ecrs τ2.56/s0.03746, nspin τ14.98/s0.0).

### 6-week τ_p qualifying counts (realized MCPC > τ_p, any product; /2016 intervals)
Source: `data/audit/w5r_run.json` → `week_qualifying_counts`.

| Week (Mon) | qualifying | per-product {regup, rrs, ecrs, nspin} |
|---|---:|---|
| 2026-04-27 | 341 | 172 / 46 / 251 / 190 |
| 2026-05-04 | 187 | 46 / 8 / 174 / 147 |
| 2026-05-11 | 200 | 77 / 69 / 188 / 158 |
| 2026-05-18 | 234 | 58 / 36 / 228 / 203 |
| 2026-05-25 | 280 | 134 / 79 / 254 / 239 |
| 2026-06-01 | 376 | 261 / 163 / 327 / 323 |

### The $2.53 re-pin story (ADR 0013)
Source: **ADR 0013 §Context / §Decision / §V2**.

| Value | What it is |
|---|---|
| $238,376.27 → $238,378.80 (**+$2.53**) | eval baseline shift on rebuild |
| AS-only; energy byte-identical **$159,021** | shift is settlement-side, not energy |
| params identical to **6 decimals** | τ_p 3.5600/2.7100/2.5600/14.9800; s_p 0.151955/0.001259/0.037460/0.000000; Δs_p = 0 on all four |
| realized-AS divergence **≤ 0.0004 $/MW** across train | cosmetic, not parameter-perturbing |

---

## 5. W5-B precheck — evening-peak LMP bias stability (NO-GO)

Window: **HoD 0–1 UTC (first 24 intervals); bias = forecast − realized; bias<0 = under-forecast** — `data/audit/w5b_precheck.json` → `window`.

### Per-panel evening-peak bias (all 7 panels), $/MWh
Source: `data/audit/w5b_precheck.json` → `panels[*].panel_bias`.

| Panel | panel_bias | sign |
|---|---:|:--:|
| eval (Apr 20–26) | **−48.01** | − |
| Apr 27–May 3 (scar-conf) | **+30.02** | + |
| May 4–10 (calm) | +18.94 | + |
| May 11–17 | +14.70 | + |
| May 18–24 | −1.31 | − |
| May 25–31 | −3.94 | − |
| Jun 1–7 (scar-primary) | −16.17 | − |

### Cross-panel stats
Source: `data/audit/w5b_precheck.json` → `cross_panel`.

| Value | What it is | Field |
|---|---:|---|
| 4 neg / 3 pos, **3 sign-flips** | instability | `n_negative`, `n_positive`, `sign_flips` |
| **mean −$0.82/MWh** | cross-panel mean (≈0) | `mean` (−0.82312) |
| median −$1.31 | | `median` (−1.30584) |
| min −$48.01 / max +$30.02 | swing range | `min` / `max` |
| **CV ≈ 29.24** | coefficient of variation (mean≈0 → huge) | `cv` (29.2406) |

- **Eval HoD values −$48.77 / −$47.25** (HoD 0 / HoD 1) — `w5b_precheck.json` → `eval_crosscheck` (`hod0` −48.7654, `hod1` −47.2486).
- **Apr 25 single-day −$377** — `w5b_precheck.json` → `panels["eval (Apr 20–26)"].per_day["2026-04-25"].bias` (−376.67); the same scarcity day driving the AS lever (ADR 0015).
- **Recommendation (verbatim start):** "NO-GO — the evening-peak LMP bias FLIPS SIGN across panels (4 negative / 3 positive, 3 flips)…" — `w5b_precheck.json` → `recommendation`.

---

## 6. Reproducibility anchors

### DOIs
Source: `docs/decisions/0016-zenodo-v02-deposit.md`; `README.md` §Dataset.

| Value | What it is |
|---|---|
| **10.5281/zenodo.21178739** | v0.2 version DOI (canonical reproduction target; published 2026-07-03) |
| **10.5281/zenodo.20204994** | v0.1 version DOI (historical) |
| **10.5281/zenodo.20204993** | concept DOI (resolves to latest = v0.2) |

### Key commit SHAs (verified via `git log -1 -- <file>`)
| SHA | ADR | Subject |
|---|---|---|
| **6677525** | ADR 0015 | forecaster bias non-stationary; static fix not bankable |
| **20d62ca** | ADR 0014 | AS anchor shrinkage fails out-of-sample replication |
| **a024b6c** | ADR 0013 | baseline re-pin to canonical-faithful build |
| **b6b031e** | ADR 0012 | scarcity-conditioned DAM AS anchor shrinkage |

(All four chunk-listed SHAs verified correct against the repo. Additional: `f2af16f` = ADR 0016 / Zenodo v0.2 deposit note, current `main` head.)

### Repo + ADR index
- Repo URL: **https://github.com/karthikmattu06-hue/ercot-rtcb-bench**
- ADR index in `docs/decisions/`: **0001, 0002, 0003, 0004, 0006, 0007, 0008, 0009, 0010, 0011, 0012, 0013, 0014, 0015** present (**0005 does not exist** — never assigned), plus **0016** (Zenodo v0.2 deposit note). "0001–0015 confirmation": confirmed present **except 0005**.

---

## 7. Scoping statement — verbatim from ADR 0015 (§"Scope of the claim")

> The non-stationarity finding is supported **within the observed window only: 7 panels,
> Apr–Jun 2026, early RTC+B.** Seasonal generalization — in particular summer ERCOT
> scarcity, a materially different regime — is **unestablished and named as an open
> thread.** The claim is not to be stated past this evidence.

(Source: `docs/decisions/0015-forecaster-bias-nonstationary.md`, §"Scope of the claim (calibration — binding)", lines 65–68. Bold emphasis as in the original.)

Companion framing line (ADR 0015 §Open threads → Blog #2): *"single-panel BESS-bidding
backtests overstate gains; two top levers evaporate under pre-registered multi-panel
replication."*

---

## 8. NOT FOUND / provenance cautions — do not cite blind

- **ΔAS oracle leg has two committed values:** ADR 0010 **+$36,393** (CF-B $274,770,
  interaction −$2,194) vs `docs/results_w4a.md` **+$37,082** (CF-B $275,458, interaction
  −$870). Same quantity, two documents. Use **$36,393** (ADR 0010; carried into W5-A/ADR
  0012). Flagged, not reconciled (no recomputation).
- **Stochastic-LP five-method row (238,376)** predates the ADR 0013 re-pin; the canonical
  forward value is 238,378.80. The other four methods (PF/EV/DAM/DFL) have **no re-pinned
  restatement** in a committed artifact — cite the `results_w3d.md` values as-is (pre-repin
  vintage) and do not imply they were re-run post-rebuild.
- **PF eval total differs by artifact:** $351,612 (`results_w3d.md`/`results_w4a.md`,
  W3-D/W4 vintage) vs $351,329 (`w5r_run.json` eval panel, post-rebuild). Cite with the
  matching baseline vintage; do not mix.
- No figure requested by the chunk was entirely absent from committed artifacts.
