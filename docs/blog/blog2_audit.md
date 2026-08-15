# Blog #2 — Number & Claim Audit (draft v2)

**Audited file:** `docs/blog/blog2_draft_v2.md` (unmodified — verification only)
**Reference:** `docs/blog2_facts.md` (facts pack, commit `7ec7aa4`) + the committed artifacts it points to
**Branch:** `blog2-facts` · **Date:** 2026-08-10
**Method:** read-only. No recomputation, no re-runs. Where the pack was insufficient, the
underlying committed artifact was read directly (ADR bodies, `data/audit/*.json`, `README.md`).
Arithmetic on already-published figures (sums, ratios) is used only as a consistency check
and is labelled as such.

**Status legend**
- **PASS** — value/claim matches a pack entry or a committed artifact.
- **FLAG** — wrong, unsupported, or misleading as written (minimal correction proposed in §6).
- Rounding and prose restatement are treated as acceptable; a rounding is flagged only if it
  distorts by >1% or reverses a sign/direction.

---

## 1. Numbers — dollar figures, percentages, dates, counts, DOIs

| # | Line | Draft statement | Source | Status |
|---|---:|---|---|:--|
| N1 | 1 | Title "The $58k That Wasn't" | pack §2: $21,479 + $36,393 = $57,872 | PASS |
| N2 | 7 | "In December 2025, ERCOT switched to a new market design (RTC+B)" | `README.md:7` "went live on December 5, 2025"; `docs/dataset-card.md:12` | PASS (not in pack; committed artifact) |
| N3 | 7 | "Every five minutes, prices update" | `docs/dataset-card.md:12` "5-minute granularity" | PASS |
| N4 | 9 | "test week (April 20 to 26, 2026)" | pack §1: eval panel Apr 20–26, 2026 (168 h) | PASS |
| N5 | 9 | "it earned $238,376" | pack §1: $238,376.27, `w5a_eval.json → phase3.baseline.revenue_total` | PASS |
| N6 | 11 | "That version earned $351,612" | pack §1 five-method table: PF LP 351,612 | PASS |
| N7 | 11 | "The gap between the two, about $113,000" | pack §2: headroom $113,236 (rounding −0.21%) | PASS |
| N8 | 15 | "that $113k gap" | pack §2 | PASS |
| N9 | 17 | "AS price errors: $36,393" | pack §2 Level 1: ΔAS +$36,393 (ADR 0010 §Phase 2) | PASS — correct choice vs the $37,082 variant flagged in pack §8 |
| N10 | 18 | "An evening price bias: $21,479" | pack §2 Level 1: ΔLMP +$21,479 (19.0%) | PASS |
| N11 | 18 | "about $48/MWh too low" | pack §5: eval `panel_bias` −48.01; bias<0 = under-forecast | PASS |
| N12 | 18 | "during the 7 to 8pm peak" | ADR 0010 line 102: "HoD 0 and 1 UTC (7–8 pm CDT, the evening energy peak)"; line 148 same label | PASS — repo's own local-time label |
| N13 | 20 | "about $58k of measured forecast error" | pack §2: 21,479 + 36,393 = 57,872 | PASS |
| N14 | 26 | "the $36k of AS price error" | pack §2 | PASS |
| N15 | 30 | "Four fitted parameters total" | ADR 0012 line 33 "**4-parameter**, per-product…"; line 47 "One parameter per product, 4 total" (s_p fitted; τ_p = fixed train q90) | PASS — pack §3's table lists τ_p *and* s_p (8 values), but only the four s_p are fitted |
| N16 | 30 | "chosen to cancel the measured overshoot on training data" | pack §3: train Jan 23–Apr 13; ADR 0012 line 46 method-of-moments, high-regime bias → ~0 | PASS |
| N17 | 32 | "earned an extra $18,271" | pack §3: `phase3.delta_w5a` (18271.390) | PASS |
| N18 | 32 | "Half the theoretical ceiling" | pack §3: `recovery_fraction` 0.502058 (50.2%) | PASS |
| N19 | 34 | "April 25, a scarcity day worth +$18.7k on its own" | pack §3: Apr 25 +$18,694 (`phase3.per_day_delta`) | PASS |
| N20 | 34 | "the same week had two losing days" | `w5a_eval.json → phase3.per_day_delta`: exactly two negative days — Apr 22 −1,155.0, Apr 24 −5,524.1 | PASS (count verified against artifact) |
| N21 | 36 | "three more weeks" | pack §4: 3 replication panels | PASS |
| N22 | 40 | Apr 20–26 "+$18,270" | pack §4 cross-panel table (re-pinned baseline) | PASS |
| N23 | 41 | Apr 27–May 3 "+$6,303" | pack §4 | PASS |
| N24 | 42 | Jun 1–7 "−$4,765" | pack §4 | PASS |
| N25 | 43 | May 4–10 "−$10,619" | pack §4 | PASS |
| N26 | 40–43 | Panel date ranges (Apr 20–26, Apr 27–May 3, Jun 1–7, May 4–10) | pack §4 panel labels; ADR 0014 §Results | PASS |
| N27 | 53 | "the $21.5k target" | pack §2: $21,479 (+0.1%) | PASS |
| N28 | 55 | "seven weeks of clean data" | pack §5: 7 panels in `w5b_precheck.json` | PASS |
| N29 | 57 | "Four weeks the forecast was too low, three weeks too high" | pack §5: `n_negative` 4 / `n_positive` 3; window def "bias<0 = under-forecast" → direction correct | PASS |
| N30 | 57 | "the bias was $0.82/MWh" | pack §5: cross-panel mean **−**$0.82/MWh (−0.82312) | **FLAG** — sign dropped (F4) |
| N31 | 57 | "The scary −$48/MWh figure came from one day … April 25" | pack §5: Apr 25 −$376.67; artifact `w5b_precheck.json → panels[eval].per_day`: other six days −9.04, −14.40, +23.72, −0.96, +16.37, +24.94 (mean +6.8) vs panel −48.01 | PASS — single-day dominance confirmed |
| N32 | 71 | "recovered 50% of a measured ceiling on one week" | pack §3: 50.2% | PASS |
| N33 | 71 | "and lost money over four" | pack §4: 4 panels total sum **+$9,189**; 3 new panels sum **−$9,081**; losses in 2 of 3 new panels | **FLAG** — wrong under either reading (F2) |
| N34 | 77 | "seven weeks of data from April to June 2026, the first months of the new market design" | pack §7 (ADR 0015 scope): "7 panels, Apr–Jun 2026, early RTC+B" | PASS |
| N35 | 79 | DOI `10.5281/zenodo.21178739` | pack §6: v0.2 version DOI; `README.md:34`; ADR 0016 §Decision | PASS |
| N36 | 79 | Repo URL `github.com/karthikmattu06-hue/ercot-rtcb-bench` | pack §6 | PASS |
| N37 | 81 | "$238,376 … later restated to $238,378.80 after a data rebuild … perfect-foresight bound $351,612" | pack §1 + §4 re-pin story (ADR 0013, +$2.53) | PASS |
| N38 | 65 | "the $113k gap" (restated) | pack §2 | PASS |

---

## 2. Directional / factual claims

| # | Line | Draft statement | Source | Status |
|---|---:|---|---|:--|
| D1 | 11 | The gap "is what a perfect forecaster would be worth for that week" | pack §2 headroom definition (Stochastic → PF) | PASS |
| D2 | 22 | "These numbers are ceilings … the value of replacing the forecast with the truth" | ADR 0012 lines 12–14: "That figure is an **oracle bound** … not a capturable estimate"; pack §3 `oracle_bound` | PASS |
| D3 | 28 | "the system had no real AS price forecaster … took the day-ahead market's own AS prices as its prediction" | ADR 0012 line 16: "The v0.1 AS 'forecaster' is not a model — AS prices are the **DAM AS MCPC anchor**"; `results_w5a_diagnostic.md:25` | PASS |
| D4 | 28 | "and added some historical noise" | ADR 0012 lines 17–18: "plus net-load-analog (RT−DAM) residuals from the shared whole-day bootstrap, clipped ≥0, **no jitter**"; `results_w5a_diagnostic.md:37` "AS gets none"; ADR 0007 lines 69–70 (both jitter forms rejected) | **FLAG** — substance right, wording collides with the explicit "no jitter" record (F5) |
| D5 | 28 | "The day-ahead prices ran too high" | pack §3 Phase-1: bias_dam positive on all five products (+0.19 to +3.86) | PASS |
| D6 | 28 | "almost all of the overshoot happened in a small number of tight, high-demand hours" | pack §3: top-decile share 96.6–99.9%; ADR 0012 line 21: "~97–100% … sits in the top decile of intervals (high net-load / high LMP)" | PASS ("high-demand" ≙ "high net-load", the ADR's own wording) |
| D7 | 28 | "Ordinary hours were fine." | ADR 0012 line 22: "calm hours are ≈ 0"; pack §3 quartile row: Q1–Q3 mild (+0.0 to +2.6) | PASS |
| D8 | 30 | "when day-ahead AS prices spike above their normal range, shrink them toward it" | ADR 0012 lines 40–44: two-regime rule, quote > τ_p → τ_p + s_p·(quote − τ_p), τ_p = train q90 | PASS |
| D9 | 34 | "the gain came almost entirely from one day" | `w5a_eval.json`: Apr 25 +$18,694 vs panel net +$18,271 (single day exceeds the net) | PASS |
| D10 | 34 | "a rule I had written down earlier, before seeing any of these numbers … no claims until the result repeats on new data" | ADR 0010 (dated **2026-06-09**) line 157: "Replication across multiple evaluation windows is needed before v0.2 roadmap decisions"; the +$18,271 result is ADR 0012, dated **2026-06-11** | PASS — rule predates the result by 2 days |
| D11 | 36 | "three more weeks, chosen by a rule fixed in advance (most scarcity, least, one more high-scarcity)" | ADR 0014 lines 15–16: "three new **pre-registered** panels (two scarcity, one calm), with the selection metric (τ_p qualifying counts) and interpretation fixed in advance"; pack §4 counts: Jun 1 = 376 (max), May 4 = 187 (min), Apr 27 = 341 (2nd) | PASS |
| D12 | 36 | "with the correction frozen exactly as fitted" | pack §4: `frozen_params` asserted == ADR 0012, no refit; ADR 0014 line 14 | PASS |
| D13 | 45 | "Two of the three new weeks lost money." | pack §4: Jun 1–7 −$4,765; May 4–10 −$10,619; Apr 27–May 3 +$6,303 | PASS |
| D14 | 45 | "the week with the *most* scarcity lost money" | ADR 0014 finding 1: "the **most-scarce week (Jun 1–7) loses**"; pack §4 qualifying counts (376 = highest) | PASS |
| D15 | 47 | "The day-ahead market's high AS prices are a prediction that scarcity is coming." | ADR 0014 line 39; ADR 0015 lines 30–33 | PASS |
| D16 | 47 | "In weeks where scarcity failed to materialize, that assumption paid off." | ADR 0014 lines 38–42 splits Δ>0 / Δ<0 on whether the **forecast** AS scarcity realized in RT — *not* on calm-vs-scarce. Both Δ>0 panels are scarcity panels; the **calm** week (May 4–10) is the **largest loss** (ADR 0014 finding 4) | **FLAG** — as written, contradicted by the draft's own table (F1) |
| D17 | 47 | "In weeks where scarcity showed up for real, the correction made the battery hold back exactly when reserves were most valuable." | ADR 0014 lines 41–42: "the frozen shrink **under-commits AS in weeks where the scarcity actually realizes in RT**" | PASS |
| D18 | 47 | "It was never a fix. It was a bet, and it wins or loses depending on the week." | ADR 0014 line 39 "a directional bet that DAM over-forecasts AS"; ADR 0015 lines 40–41 "a **directional bet that wins or loses by whether scarcity realizes**" | PASS |
| D19 | 49 | "I retired it." | ADR 0014 §Decision: "**Retire** the frozen, unconditional AS anchor shrinkage as a revenue lever." | PASS — note: pack §4's quoted `verdict` string ("lever real but high-variance") is the raw JSON line; ADR 0014 is the binding decision |
| D20 | 55 | "before building anything, I measured the evening bias on every week separately" | pack §5: per-panel bias for all 7 panels, `w5b_precheck.json → panels[*].panel_bias` | PASS |
| D21 | 57 | "It flipped sign." | pack §5: `sign_flips` = 3; min −48.01 / max +30.02 | PASS |
| D22 | 57 | "That day was April 25. The same scarcity day that had propped up the first fix." | ADR 0015 line 37: "**the same scarcity day** that drove the AS lever"; pack §5 bullet | PASS |
| D23 | 59 | "the second correction was dead before I wrote a line of it" | pack §5 recommendation "NO-GO"; `docs/results_w5b_precheck.md:75` "Per the pre-registered mapping, sign flips across panels → NO-GO" | PASS |
| D24 | 65 | "My original test week contained one severe scarcity day." | ADR 0015 line 38: "W4's single eval panel (Apr 20–26) contained Apr 25, a scarcity day"; per-day artifacts show a single extreme day in both W5-A and W5-B | PASS |
| D25 | 65 | "what it measured wasn't a steady error you can subtract out … mostly the value of knowing, in advance, whether a scarcity event will happen" | ADR 0015 lines 46–49: bounds are "**EVPI-dominated, not bias-dominated** — the gap is mostly the value of *knowing whether scarcity will realize*" | PASS |
| D26 | 65 | "expected value of perfect information … no after-the-fact price adjustment can buy it" | ADR 0015 line 49; ADR 0014 §Decision "Lesson (recorded)" | PASS |
| D27 | 67 | "The forecaster roadmap used to be a list of bias corrections. Now it is one harder question: can you predict … how likely scarcity is to actually materialize?" | ADR 0015 lines 57–58 "**scarcity-realization conditioning** — a forecasting problem (predict *whether* … scarcity)"; line 77 "v0.2 = scarcity-realization conditioning, not bias correction" | PASS |
| D28 | 71 | "Battery revenue in ERCOT concentrates on scarcity days." | pack §4 panel baselines: $60,388 (calm) / $87,533 / $238,379 / $321,420 (scarcity) — 5.3× spread across seven days | PASS (supported indirectly; also general market knowledge) |
| D29 | 73 | "The replication requirement was written into my decision log before the test result existed." | ADR 0010 line 157 (2026-06-09) vs ADR 0012 (2026-06-11) — same evidence as D10 | PASS |
| D30 | 73 | "The extra test weeks were picked by a fixed rule, so I couldn't choose flattering ones." | ADR 0014 lines 15–16; `docs/results_w5r_run.md:38` "Pre-registered panels (fixed)" | PASS |
| D31 | 73 | "The correction was frozen before retesting." | pack §4 `frozen_params`; ADR 0014 line 14 "the **frozen** (τ_p, s_p) — asserted identical to ADR 0012, no refit" | PASS |
| D32 | 73 | "The pass/fail criteria were written down in advance." | ADR 0014 line 16 "interpretation fixed in advance"; `docs/results_w5r_run.md:135` "Per the pre-registered…"; `docs/results_w5b_precheck.md:75` "Per the pre-registered mapping" | PASS |
| D33 | 77 | "whether these findings hold [in summer] is an open question" | pack §7 verbatim ADR 0015 scope: seasonal generalization "**unestablished and named as an open thread**" | PASS |
| D34 | 79 | "the exact dataset behind **every number here** is archived at Zenodo (v0.2)" | ADR 0016 §Context: v0.2 reproduces the **re-pinned** baseline and "every committed audit number (`w5a`, `w5r`, `w5b_precheck`)". The W3-D/W4 figures the draft cites ($238,376, $351,612, $113,236, $36,393, $21,479) are **pre-rebuild vintage**; ADR 0016 states v0.1 "no longer reproduces the current baseline" and v0.2 is "**Not a superset**" | **FLAG** — over-claims coverage (F3) |

---

## 3. Unsupported claims (no source in pack or committed artifacts)

Market-mechanics background (paragraph at line 7: how energy arbitrage and AS work,
5-minute price updates, batteries bidding limited capacity) is exempt per scope and is not
listed. Project-specific items with no located source:

| # | Line | Statement | Note |
|---|---:|---|---|
| U1 | 73 | "This is ordinary scientific hygiene, and it is still uncommon in how bidding strategies get evaluated." | Claim about *industry evaluation practice*. No source in the pack or repo; not a market-mechanics fact. Unverifiable as stated. |
| U2 | 77 | "an open question I plan to test now that summer data exists" | Forward-looking intention, not a result. The *open question* itself is sourced (pack §7); the plan and the "summer data exists" premise are not in any artifact (v0.2 coverage ends 2026-06-09, ADR 0016). |
| U3 | 3 | "[first post](#)" | Placeholder link — no factual content, but unresolved before publish. |

No other factual statement in the draft lacked a pack entry or committed artifact.

---

## 4. Vintage discipline — PASS

| Check | Result |
|---|:--|
| Pre-repin baseline $238,376 used together with PF $351,612 (both W3-D/W4 vintage) | PASS — lines 9/11/81 |
| Re-pin note present | PASS — line 81 states $238,378.80 and attributes it to a documented data rebuild (ADR 0013) |
| Post-rebuild PF $351,329 (pack §8) not mixed in | PASS — never cited |
| Re-pinned baseline $238,378.80 not attached to the W4 decomposition | PASS |
| $18,271 (line 32, W5-A pre-repin) vs $18,270 (line 40 table, W5-R re-pinned) | PASS — both committed; ADR 0014 line 30 reconciles them explicitly ("+$18,270 ≈ +$18,271, confirming the ADR 0013 shift was cosmetic") |
| ΔAS leg: $36,393 (ADR 0010) chosen over $37,082 (`results_w4a.md`) | PASS — the carried-forward value, as pack §8 directs |

---

## 5. Summary

| | Count |
|---|---:|
| Claims checked (numbers) | 38 |
| Claims checked (directional/factual) | 34 |
| **Total claims checked** | **72** |
| PASS | 67 |
| FLAG | 5 |
| Unsupported-claims list | 3 items (U1–U3) |
| Vintage-discipline checks | 6, all PASS |

Two flags are substantive (F1, F2), one is moderate (F3), two are minor (F4, F5).
No dollar figure, percentage, date, or DOI was found to be sourced from a value that does
not exist in a committed artifact.

---

## 6. Flag list with suggested minimal corrections

### F1 — line 47: mechanism sentence contradicted by the draft's own table (substantive)

> "In weeks where scarcity failed to materialize, that assumption paid off."

The two winning panels (eval, Apr 27–May 3) are both **scarcity** panels; the **calm** week
(May 4–10, fewest qualifying intervals: 187) is the **largest loss** at −$10,619. ADR 0014
lines 38–42 conditions Δ>0 vs Δ<0 on whether the *day-ahead forecast's* AS scarcity actually
**realized in RT**, not on whether the week was calm. ADR 0014 finding 4 records the calm
downside separately ("Calm downside unbounded vs the precedent").

**Minimal correction:** *"In weeks where the day-ahead's forecast scarcity failed to show up
in real time, that assumption paid off."* — and, if a sentence can be spared, note that the
calm week lost anyway, which is why the pattern isn't simply calm-good / scarce-bad.

### F2 — line 71: "lost money over four" (substantive, number)

> "My correction recovered 50% of a measured ceiling on one week and lost money over four."

There are four panels in total, not five: eval + three replication weeks. Arithmetic on the
pack §4 figures: all four sum to **+$9,189** (net gain), and the three *new* weeks sum to
**−$9,081**, losing in **2 of 3**.

**Minimal correction:** *"…recovered 50% of a measured ceiling on one week and lost money on
two of the three weeks that followed."*

### F3 — line 79: "the exact dataset behind every number here" (moderate)

ADR 0016 scopes v0.2 to the ADR 0013 canonical rebuild and the `w5a` / `w5r` / `w5b_precheck`
audit numbers, states explicitly that it is "**Not a superset**", and notes that v0.1
"predates that rebuild and no longer reproduces the current baseline". The W3-D/W4 figures
the post leans on ($238,376, $351,612, $113,236, $36,393, $21,479) are pre-rebuild vintage.

**Minimal correction:** *"…and the canonical dataset behind the replication results is
archived at Zenodo (v0.2)"* — dropping "every number here", or adding "(the pre-rebuild
figures above predate that deposit; see ADR 0013/0016)".

### F4 — line 57: sign dropped on the cross-panel mean (minor)

> "Averaged across weeks, the bias was $0.82/MWh, essentially zero."

Pack §5: mean is **−$0.82/MWh**. Magnitude and the "essentially zero" reading are right; the
sign is the direction the rest of the paragraph turns on (negative = forecast too low).

**Minimal correction:** *"the bias was −$0.82/MWh"*.

### F5 — line 28: "added some historical noise" (minor)

The mechanism is analog RT−DAM residuals drawn from a whole-day bootstrap (ADR 0012 lines
17–18). "Noise" reads as jitter, which the repo explicitly does **not** apply to AS —
"no jitter" (ADR 0012 line 18), "AS gets none" (`results_w5a_diagnostic.md:37`), both jitter
forms rejected in ADR 0007 lines 69–70.

**Minimal correction:** *"…and added leftover errors from similar past days"* or
*"…added historical residuals from similar days"*.

---

## 7. Notes for the fix pass (no action taken here)

- **N15 / "four fitted parameters"** is correct as written (ADR 0012: four fitted `s_p`,
  one per product; `τ_p` is a fixed train-q90 threshold, not fitted). Pack §3's table shows
  both columns and could invite a spurious "eight" correction — it should not be made.
- **N12 / "7 to 8pm"** is the repo's own local-time label for HoD 0–1 UTC (ADR 0010 lines
  102, 148). It covers two UTC hours; if a reader-facing precision tweak is ever wanted,
  "7–9pm CT" is the literal span, but the draft matches the committed wording and is not
  flagged.
- **D19** — pack §4 quotes the raw `w5r_run.json` verdict ("lever real but high-variance; no
  v0.2 claim without more panels"). ADR 0014's Decision (retire) supersedes it. The draft
  follows ADR 0014; no change needed.

**End of audit. No edits were made to `blog2_draft_v2.md`.**
