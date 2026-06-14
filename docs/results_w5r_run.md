# W5-R-run — Out-of-Sample Replication of the AS Anchor Lever

**Verdict: the lever does NOT robustly replicate.** It is high-variance and
one-day-driven on every panel; the two scarcity panels disagree in sign (the
*most-scarce* week loses); and the calm-week downside exceeds the single-panel
precedent. **No v0.2 claim is warranted on this evidence.**

**Solver:** Gurobi. **Params:** FROZEN, no refit.

---

## Frozen parameters (asserted == ADR 0012, no refit)

Loaded from `w5a_eval.json` and asserted equal before any run:

| Product | τ_p | s_p |
|---|---:|---:|
| regup | 3.560 | 0.15195465 |
| rrs | 2.710 | 0.00125885 |
| ecrs | 2.560 | 0.03746033 |
| nspin | 14.980 | 0.00000000 |

All four match ADR 0012 / W5-R-verify exactly.

## Selection — 6-week τ_p qualifying counts (auditability)

Qualifying interval = realized RT MCPC > τ_p for ANY product.

| Week | Qualifying / 2016 | regup | rrs | ecrs | nspin |
|---|---:|---:|---:|---:|---:|
| Apr 27–May 3 | 341 | 172 | 46 | 251 | 190 |
| May 4–10 | **187 (calm)** | 46 | 8 | 174 | 147 |
| May 11–17 | 200 | 77 | 69 | 188 | 158 |
| May 18–24 | 234 | 58 | 36 | 228 | 203 |
| May 25–31 | 280 | 134 | 79 | 254 | 239 |
| Jun 1–7 | **376 (scarcity)** | 261 | 163 | 327 | 323 |

Pre-registered panels (fixed): scarcity-primary **Jun 1–7** (376), calm **May 4–10**
(187), scarcity-confirmatory **Apr 27–May 3** (341).

---

## Per-panel results

PF here = `perfect_foresight` energy+AS (no terminal term), computed consistently per
panel for headroom context (differs from the canonical $351,612 eval citation).

### Apr 20–26 — eval (restated baseline, ADR 0013) — Δ **+$18,270**

Baseline $238,378.80 → corrected $256,649.24. Components Δ: E +$13,494 / AS +$3,947 /
Liq +$829. **Both E and AS up.** Reproduces W5-A on the restated baseline (committed
+$18,271). PF headroom $112,950 → 16.2%. Worst day Apr 24 −$5,524.

| Day | Δ | (E / AS) | qual |
|---|---:|---|---:|
| 04-20 | +1,420 | +793 / +627 | 59 |
| 04-21 | +995 | +1,013 / −18 | 58 |
| 04-22 | −1,155 | −1,328 / +173 | 0 |
| 04-23 | +1,034 | +971 / +62 | 0 |
| 04-24 | **−5,524** | −5,958 / +433 | 76 |
| 04-25 | **+18,694** | +16,067 / +2,627 | 41 |
| 04-26 | +1,978 | +1,936 / +42 | 0 |

→ +$18.7k on **one day** (Apr 25); the other six net ≈ −$0.4k.

### Jun 1–7 — scarcity (primary, most qualifying) — Δ **−$4,765** ❌

Baseline $87,533 → corrected $82,768. Components Δ: E −$2,610 / AS −$3,070 / Liq +$915.
**Both E and AS DOWN.** PF headroom $104,396 → −4.6%. Worst day Jun 4 −$8,755.

| Day | Δ | (E / AS) | qual |
|---|---:|---|---:|
| 06-01 | −36 | −36 / +0 | 42 |
| 06-02 | +499 | +466 / +32 | 0 |
| 06-03 | +5,590 | +7,580 / −1,991 | 24 |
| 06-04 | **−8,755** | −8,197 / −558 | 50 |
| 06-05 | −2,439 | −2,405 / −34 | 52 |
| 06-06 | +1,909 | +2,647 / −738 | 177 |
| 06-07 | −2,446 | −2,665 / +219 | 31 |

→ The **most-scarce** week (376 qualifying) **loses money**. The highest-qualifying day
(Jun 6, 177) is +$1.9k, but Jun 4 (qual 50) drives −$8.8k — scarcity-day concentration
does **not** hold.

### May 4–10 — calm — Δ **−$10,619** ❌ (downside NOT bounded)

Baseline $60,388 → corrected $49,769. Components Δ: E −$492 / AS −$3,413 / Liq −$6,714.
**Both E and AS down.** PF headroom $56,409 → −18.8%. Worst day May 5 −$7,514.

| Day | Δ | (E / AS) | qual |
|---|---:|---|---:|
| 05-04 | +2,249 | +3,735 / −1,486 | 19 |
| 05-05 | **−7,514** | −6,330 / −1,184 | 43 |
| 05-06 | −5,235 | −5,333 / +98 | 41 |
| 05-07 | +4,223 | +4,285 / −62 | 3 |
| 05-08 | −2,270 | −2,266 / −3 | 36 |
| 05-09 | +942 | +984 / −42 | 32 |
| 05-10 | +3,699 | +4,434 / −735 | 13 |

→ Calm-week loss is **large** (−18.8% of headroom). Worst day **−$7,514 exceeds the
W5-A Apr 24 precedent (−$5,524)** — downside is **not bounded**.

### Apr 27–May 3 — scarcity (confirmatory) — Δ **+$6,303** ✅

Baseline $321,420 → corrected $327,723. Components Δ: E +$5,445 / AS +$4,115 /
Liq −$3,257. **Both E and AS up.** PF headroom $93,198 → 6.8%. Worst day Apr 27 −$15,025.

| Day | Δ | (E / AS) | qual |
|---|---:|---|---:|
| 04-27 | **−15,025** | −15,436 / +411 | 88 |
| 04-28 | **+18,903** | +15,480 / +3,423 | 52 |
| 04-29 | +4,497 | +4,565 / −68 | 15 |
| 04-30 | −4,226 | −5,029 / +803 | 62 |
| 05-01 | +1,836 | +1,654 / +182 | 44 |
| 05-02 | +3,131 | +3,556 / −425 | 67 |
| 05-03 | +444 | +655 / −211 | 13 |

→ Net positive, but a −$15.0k / +$18.9k single-day swing (Apr 27 / 28) dwarfs the
+$6.3k total — again one-day-driven.

---

## Cross-panel synthesis

| Panel | Δ | Δ / PF-headroom | worst single day | E & AS both up |
|---|---:|---:|---:|:---:|
| Apr 20–26 (eval, restated) | **+$18,270** | 16.2% | −$5,524 | ✅ |
| Jun 1–7 (scarcity, primary) | **−$4,765** | −4.6% | −$8,755 | ❌ |
| May 4–10 (calm) | **−$10,619** | −18.8% | −$7,514 | ❌ |
| Apr 27–May 3 (scarcity, confirm) | **+$6,303** | 6.8% | −$15,025 | ❌ (E↑AS↑ at panel level) |

### Does the lever replicate? **No — high-variance, one-day-driven, sign-unstable.**

1. **Scarcity panels disagree in sign.** Apr 27–May 3 +$6,303 vs Jun 1–7 −$4,765 — and
   the **primary** (most-scarce, 376-qualifying) week **loses**. Per the pre-registered
   rule (one positive / one negative scarcity panel) the lever is "real but
   high-variance; no v0.2 claim without more panels."
2. **Calm downside is not bounded.** May 4–10 loses $10,619 (−18.8% of headroom), worst
   day −$7,514 — *larger* than the W5-A precedent the single panel suggested. The lever
   can lose materially when there is little AS scarcity to correct.
3. **One-day-driven on every panel.** Each panel's net is the residual of ±$5–19k
   single-day swings (eval +$18.7k on Apr 25; Apr 27–May 3 a −$15.0k/+$18.9k Apr 27/28
   swing; Jun 4 −$8.8k; May 5 −$7.5k). W5-A's headline was not panel-robust — it was a
   favorable single day, and that fragility is universal here.
4. **Mechanism — the ADR 0012 symmetric risk materializes.** Where Δ>0 (eval,
   Apr 27–May 3) both energy and AS rise (the reallocation mechanism). Where Δ<0
   (Jun 1–7, May 4–10) both fall: shrinking the DAM AS anchor **under-commits AS in
   weeks where the scarcity actually realizes** in RT — exactly the symmetric
   under-commitment risk flagged in ADR 0012. The lever is a bet that DAM over-forecasts
   AS; that bet wins on some weeks and loses on others, with no stable edge here.

**Conclusion:** the W5-A AS anchor shrinkage, frozen and applied out-of-sample, is
**not a reliable positive-expectation intervention** on this evidence — 2 of 3 new
panels lose, the most-scarce week loses, and the calm-week downside exceeds the
single-panel precedent. The +$18,271 / 50.2% W5-A result was favorable-panel- (indeed
favorable-day-) specific. **Do not claim the lever in v0.2/preprint.** Next steps
(for chat): treat the AS over-forecast as real but the *shrinkage* as too blunt
(consider scarcity-realization-conditioned or magnitude-capped variants), and/or move
to the W5-B LMP evening-peak lever.

**Files:** `scripts/backtest_w5r_run.py` (+ reused `scripts/backtest_w5r.py`), audit
`data/audit/w5r_run.json`.

**HARD STOP** — ADR (replicates / doesn't) + any merge decided in chat.
