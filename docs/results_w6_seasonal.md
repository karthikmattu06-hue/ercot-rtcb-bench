# W6 Results — July Seasonal Test of the ADR 0015 Non-Stationarity Claims

**Chunk:** W6 (pre-registered summer replication) · **Branch:** `w6-seasonal` · **Date:** 2026-08-10
**Scope:** extend data through Aug 3, then test the two ADR 0015 claims on summer panels.
**No refit, no fix-building, no new correction, no ADR.** This document reports; interpretation
against the pre-registered criteria happens in chat.

Artifacts: `data/audit/w6_seasonal.json` (all figures), `data/audit/w6_pull_log.json`
(fetch ledger), `scripts/pull_w6.py`, `scripts/w6_seasonal.py`.

---

## Headline

**July 2026 was mild.** Four of the five candidate July weeks carry 6–27 τ_p-qualifying
intervals against a spring range of 187–376; the single most-scarce July week (221) sits
*mid-spring-range* and below **both** spring scarcity panels (341, 376). The "materially
different summer scarcity regime" ADR 0015 named as its open thread **did not occur in the
window now available**. Pre-registered criterion 3 therefore fires: this chunk **bounds**
the ADR 0015 claim more than it tests it.

Within that bound, both claims under test **held**: the evening-peak LMP bias keeps flipping
sign with a near-zero mean across the full 12-panel set, and the frozen AS lever remains
mixed-sign and single-day-concentrated rather than systematically profitable.

---

## Phase 0 — Pull, integrity, no-regression

### Pull (W5-R-pull discipline, reused verbatim)

`scripts/pull_w6.py` is a thin wrapper over the proven `pull_w5r` infra — only the window,
the reassembly months, and the log path differ. Completeness-based skip, atomic writes
(tmp + `os.replace`), checkpoint-and-continue, ≥2s throttle, and schema-drift STOP all carry
over unchanged.

| | |
|---|---|
| Window | 2026-06-08 → 2026-08-03 inclusive (Jun 8 re-verified for completeness) |
| Products | 7 (`rt_lmp`, `sced_mcpc`, `dam_spp`, `dam_as`, `wind`, `solar`, `load_actual`) |
| **pulled** | **393** |
| skipped (already complete) | 6 |
| empty | 0 |
| **failed** | **0** |
| schema drift | none (would have raised and stopped) |
| Reassembled months | 2026-06, 2026-07, 2026-08 |

**Backup taken before any reassembly**, per the binding rule:
`~/ercot-w6-backup-preassemble/` — full copy of all 18 pre-W6 forecaster parquets plus
`SHA256SUMS_pre_w6.txt`.

### Coverage after the pull

| Series | Latest finite timestamp |
|---|---|
| RT prices (LMP + 5× MCPC) | **2026-08-04 04:55 UTC** |
| DAM AS MCPC / SPP | **2026-08-04 04:00 UTC** |
| System conditions (net load) | 2026-08-11 04:00 UTC |

Every candidate July week plus its Sun+1 UTC tail is covered.

### Per-week gap gate (≤0.5% missing, any series)

| Candidate week (Mon–Sun) | Worst-series gap % | Eligible |
|---|---:|:--:|
| Jun 29 – Jul 5 | 0.000% | ✅ |
| Jul 6 – Jul 12 | 0.050% | ✅ |
| Jul 13 – Jul 19 | 0.000% | ✅ |
| Jul 20 – Jul 26 | 0.000% | ✅ |
| Jul 27 – Aug 2 | 0.099% | ✅ |

**5 of 5 eligible.** The `<1 eligible week → STOP` gate did not fire.

### No-regression spot-check — **PASS**

Eval panel Apr 20–26 re-run with the flag OFF on the rebuilt data:

```
eval baseline = $238,378.80229    target $238,378.80 (ADR 0013)
drift = +$0.00229                 tolerance ±$1.00        GATE: PASS
components: E $159,020.79 / AS $72,480.28 / Liq $6,877.73
```

The canonical baseline survives the July reassembly.

> **Data-vintage note (reported, not corrected).** Re-running the W5-B bias harness *before*
> the pull reproduced all seven committed spring panels to the cent. *After* reassembly, six
> still match exactly but **Jun 1–7 moved −16.17 → −16.15** (Δ $0.02, ~0.1%). Rewriting the
> 2026-06 parquet slightly revised that week's realized inputs. It changes no sign, no
> ordering, and no finding; the eval-panel no-regression gate above is the binding check and
> it passes. Flagged for provenance, not reconciled (no recomputation of committed W5-B).

---

## Phase 1 — Selection (mechanical, W5-R rules)

Metric: τ_p-qualifying interval = realized RT MCPC > **frozen** τ_p for **any** of the four
corrected products, out of 2,016 intervals per week.

### Frozen parameters — asserted equal to ADR 0012 at runtime

```
regup  tau=  3.560  s=0.15195465087890625  == ADR 0012 OK
rrs    tau=  2.710  s=0.00125885009765625  == ADR 0012 OK
ecrs   tau=  2.560  s=0.03746032714843750  == ADR 0012 OK
nspin  tau= 14.980  s=0.00000000000000000  == ADR 0012 OK
All four match ADR 0012 exactly — NO refit.
```

(Assertion tolerance 1e-9 on τ_p, 1e-12 on s_p; the run aborts on drift.)

### Qualifying counts — summer against spring

| Week (Mon) | Season | Qualifying /2016 | Per-product {regup, rrs, ecrs, nspin} |
|---|:--:|---:|---|
| 2026-04-27 | spring | 341 | *(committed, w5r_run.json)* |
| 2026-05-04 | spring | 187 | *(committed)* |
| 2026-05-11 | spring | 200 | *(committed)* |
| 2026-05-18 | spring | 234 | *(committed)* |
| 2026-05-25 | spring | 280 | *(committed)* |
| 2026-06-01 | spring | 376 | *(committed)* |
| **2026-06-29** | summer | **20** | 0 / 0 / 20 / 0 |
| **2026-07-06** | summer | **27** | 3 / 0 / 20 / 14 |
| **2026-07-13** | summer | **6** | 6 / 0 / 0 / 0 |
| **2026-07-20** | summer | **221** | 198 / 124 / 168 / 139 |
| **2026-07-27** | summer | **20** | 3 / 0 / 20 / 0 |

- **Summer range 6–221** vs **spring range 187–376**.
- Selected (mechanical, most/fewest, ties→earlier): **summer scarcity panel = Jul 20–26 (221)**;
  **summer calm panel = Jul 13–19 (6)**.

The summer *maximum* (221) is below every spring week except May 4–10 (187) and May 11–17
(200) — i.e. it is a middling spring week, not a summer scarcity event. This is the evidence
for criterion 3.

---

## Phase 2A — Evening-peak LMP bias, extended

Window and quantity verbatim from W4-A / ADR 0010: evening peak = **HoD 0–1 UTC** (first 24
five-minute intervals); bias = probability-weighted forecast LMP − realized LMP;
**bias < 0 = under-forecast**.

| Panel | Season | Bias $/MWh | Sign | day-σ | Days sharing panel sign | Max abs day bias |
|---|:--:|---:|:--:|---:|:--:|---:|
| eval (Apr 20–26) | spring | **−48.01** | − | 135.0 | 4/7 | — |
| Apr 27–May 3 (scar-conf) | spring | **+30.02** | + | 53.2 | 5/7 | — |
| May 4–10 (calm) | spring | +18.94 | + | 14.2 | 6/7 | — |
| May 11–17 | spring | +14.70 | + | 24.8 | 5/7 | — |
| May 18–24 | spring | −1.31 | − | 22.1 | 4/7 | — |
| May 25–31 | spring | −3.94 | − | 34.4 | 4/7 | — |
| Jun 1–7 (scar-primary) | spring | −16.15 | − | 21.6 | 5/7 | — |
| **Jun 29–Jul 5** | summer | **−2.23** | − | 15.9 | 4/7 | 36.7 |
| **Jul 6–Jul 12** | summer | **+5.11** | + | 9.5 | 5/7 | 21.1 |
| **Jul 13–Jul 19** | summer | **+1.23** | + | 8.4 | 3/7 | 17.6 |
| **Jul 20–Jul 26** | summer | **+15.13** | + | 29.5 | 5/7 | 62.7 |
| **Jul 27–Aug 2** | summer | **−3.18** | − | 25.0 | 2/7 | 61.8 |

### Cross-panel stats

| Set | n | neg/pos | sign flips | mean | median | min | max | CV |
|---|---:|:--:|---:|---:|---:|---:|---:|---:|
| **Full (spring+summer)** | 12 | 6 / 6 | **6** | **+0.86** | −0.04 | −48.01 | +30.02 | 22.07 |
| Spring only | 7 | 4 / 3 | 3 | −0.82 | −1.31 | −48.01 | +30.02 | 29.34 |
| **Summer only** | 5 | 2 / 3 | **2** | **+3.21** | +1.23 | −3.18 | +15.13 | 2.07 |

Two observations worth carrying into interpretation:

1. **The sign keeps flipping in summer** (2 neg / 3 pos, 2 flips) and the mean stays near
   zero (+$3.21/MWh summer; +$0.86/MWh over all 12 panels, median −$0.04).
2. **Summer magnitudes are much tighter** — the whole summer span is −$3.18 to +$15.13
   against spring's −$48.01 to +$30.02. No July week contains anything like the Apr 25
   episode. Summer CV is low (2.07) only because the summer mean is not as close to zero as
   spring's, not because the sign stabilised.

---

## Phase 2B — Frozen AS lever on the summer panels

Stochastic LP, flag OFF / flag ON (frozen ADR 0012 params, asserted above) / PF, on the two
mechanically-selected summer panels.

### Summer scarcity panel — Jul 20–26 (221 qualifying)

| | Total | Energy | AS | Term.Liq |
|---|---:|---:|---:|---:|
| Baseline (flag off) | 214,203.34 | 118,178 | 84,552 | 11,474 |
| Corrected (frozen) | 219,686.38 | 122,070 | 86,143 | 11,474 |
| **Δ** | **+5,483.04** | **+3,891.97** | **+1,591.08** | +0.00 |
| PF (upper bound) | 243,484.73 | | | |

- Δ / PF-headroom = **+18.7%** (headroom $29,281.39)
- **E & AS both up: yes** — the ADR 0014 reallocation signature of a Δ>0 panel
- Worst day: **Jul 21, −$795.08**
- Per-day Δ: `07-20 +0 · 07-21 −795 · 07-22 +210 · 07-23 +5,760 · 07-24 +249 · 07-25 −12 · 07-26 +72`
- Per-day qualifying: `07-20 10 · 07-21 59 · 07-22 81 · 07-23 71 · 07-24 0 · 07-25 0 · 07-26 0`

**Single-day concentration, again.** Jul 23 alone (+$5,760) **exceeds the whole panel net**
(+$5,483) — the same signature as Apr 25 in W5-A. And the gain does **not** land on the
most-scarce day: Jul 22 carries the most qualifying intervals (81) but returns only +$210.

### Summer calm panel — Jul 13–19 (6 qualifying)

| | Total | Energy | AS | Term.Liq |
|---|---:|---:|---:|---:|
| Baseline (flag off) | 43,364.76 | 9,281 | 15,296 | 18,788 |
| Corrected (frozen) | 43,364.76 | 9,281 | 15,296 | 18,788 |
| **Δ** | **+0.00** | +0.00 | +0.00 | +0.00 |
| PF (upper bound) | 79,353.45 | | | |

- Δ / PF-headroom = **0.0%**; no worst day (every per-day Δ is exactly zero)
- Per-day qualifying: `07-13 0 · 07-14 0 · 07-15 1 · 07-16 1 · 07-17 5 · 07-18 0 · 07-19 0`

**The correction is inert here, not merely small.** Δ = $0.00 to the cent on all seven days
means the DAM AS quote never crossed τ_p, so the two-regime rule never fired. This is a
different outcome from the May 4–10 spring calm week (−$10,619), where the lever *did* fire
and lost money.

---

## Findings against the three pre-registered criteria

### Criterion 3 — "a null is informative" → **FIRES. This is the binding result.**

July 2026 did **not** contain a genuinely high-scarcity week. Four of five candidate weeks
(6, 20, 20, 27 qualifying) are an order of magnitude below the spring minimum of 187; the
most-scarce July week (221) is mid-spring-range and below both spring scarcity panels used in
W5-R (341, 376). **Summer 2026 was mild through July.** The regime ADR 0015 flagged as
materially different and unestablished did not materialise in the data now available, so this
chunk **bounds** the ADR 0015 scope rather than testing it at the intended severity. Any
seasonal-generalisation statement must still be scoped to observed weeks.

### Criterion 1 — Evening-peak LMP bias instability → **CONFIRMS ADR 0015**

The sign keeps flipping into summer (2 neg / 3 pos, 2 flips) and the mean stays near zero
(+$3.21/MWh summer; +$0.86/MWh, median −$0.04 across all 12 panels). Summer shows **no
stable, same-sign bias of consistent magnitude** — the COMPLICATES branch is not triggered.
Secondary: summer magnitudes are far tighter than spring's, with no July analogue of the
Apr 25 −$48 episode, which is consistent with (and explained by) the mildness finding.

### Criterion 2 — AS lever, no stable edge → **CONFIRMS ADR 0015** (with a mildness caveat)

Results stay **mixed and mechanism-dependent**, not consistently profitable:

- Only **one** summer panel (Jul 20–26) carried enough scarcity to constitute a test at all;
  the calm panel produced an exact **$0.00** because the lever never fired.
- The one win (+$5,483) is **single-day concentrated** — Jul 23 alone (+$5,760) exceeds the
  panel net — and the panel still contains a losing day (Jul 21, −$795).
- The gain does not track scarcity intensity: the most-scarce day (Jul 22, 81 qualifying)
  returns +$210 while a less-scarce day drives the result.
- E & AS both rise, matching the ADR 0014 Δ>0 reallocation mechanism rather than any new one.

The COMPLICATES branch required the frozen correction to **win consistently across summer
scarcity panels**. There was one such panel, and its win reproduces the very concentration
signature that sank the lever in W5-R. So the criterion is not met.

**Explicitly, per the chunk's instruction:** even had this looked stronger, a single positive
summer panel would **not** be grounds to un-retire the lever (ADR 0014 stands). It is not
grounds here either.

---

## What this chunk did **not** do

No parameter refit. No new correction built. No ADR written. Not merged to `main`. The
frozen ADR 0012 parameters were asserted equal at runtime and used as-is.

## Open thread carried forward

The summer test ADR 0015 called for still has not been run at the intended severity, because
July 2026 did not supply a high-scarcity week. August (partially covered: RT/DAM finite to
Aug 4) and September remain the natural window. Whether the two claims survive a genuine
summer scarcity regime is **still unestablished**.

---

# Appendix — W6 Exhibits (read-only; no LP runs, no refit)

Frozen τ_p asserted equal to ADR 0012 at runtime for both exhibits
(regup 3.560 · rrs 2.710 · ecrs 2.560 · nspin 14.980).

## Exhibit 1 — Monthly τ_p-crossing fractions (maturation check)

**Quantity:** fraction of hourly DAM AS quotes exceeding the frozen τ_p, per product, per
month. This is the correction's *trigger condition*: the ADR 0012 two-regime rule fires only
when the DAM quote clears τ_p. Motivation: the W6 calm panel (Jul 13–19) returned exactly
$0.00 because the quote never crossed τ.

| Month | regup | rrs | ecrs | nspin | DAM hours |
|---|---:|---:|---:|---:|---:|
| 2026-01 | **17.9%** | **18.0%** | **21.0%** | 8.9% | 738 |
| 2026-02 | 5.1% | 5.2% | 6.5% | 0.3% | 672 |
| 2026-03 | 2.8% | 2.8% | 1.7% | 1.1% | 744 |
| 2026-04 | 13.5% | 15.0% | 14.9% | 7.6% | 720 |
| 2026-05 | 10.7% | 11.1% | 13.5% | **11.0%** | 739 |
| 2026-06 | 4.2% | 4.3% | 7.4% | 4.8% | 715 |
| 2026-07 | **1.8%** | **2.6%** | 5.8% | 2.0% | 739 |

**Reading — the crossing fraction does _not_ decline monotonically, and the maturation
hypothesis is _not_ established by this exhibit.** The series falls Jan→Mar, **rebounds
Apr→May**, then falls again Jun→Jul. July is the series minimum for regup (1.8%) and rrs
(2.6%) but not for ecrs (Mar 1.7%) or nspin (Feb 0.3%).

### Why the trend reading is confounded

The DAM crossing fraction co-moves with how scarce the month actually was, so calendar time
and scarcity are not separable here:

| Month | DAM quote > τ (regup) | Realized RT MCPC > τ (any product) |
|---|---:|---:|
| 2026-01 | 17.9% | 12.3% |
| 2026-02 | 5.1% | 4.8% |
| 2026-03 | 2.8% | 5.2% |
| 2026-04 | 13.5% | 8.7% |
| 2026-05 | 10.7% | 11.5% |
| 2026-06 | 4.2% | 9.1% |
| 2026-07 | 1.8% | 3.1% |

The Apr–May rebound in the DAM series tracks the spring scarcity months, not a maturation
path. A maturation claim would need a **scarcity-normalised** measure (e.g. DAM crossing
conditional on realized scarcity level) that this exhibit does not provide.

**Status: the chunk's antecedent ("if declining") is _not_ satisfied.** The candidate
maturation mechanism is therefore recorded as **NOT ESTABLISHED by W6 evidence** — an open
question, not a finding. What the exhibit *does* establish is narrower and still useful: the
trigger condition is **strongly time-varying** (1.8%–17.9% for regup across seven months),
which is sufficient on its own to explain the Jul 13–19 inertness.

## Exhibit 2 — Winter Storm Fern date-check

### Dates

| Item | Date | Source |
|---|---|---|
| ERCOT Weather Watch issued | **2026-01-21** | ERCOT post-event report (primary) |
| Storm event period | **2026-01-23 – 2026-01-26** | corroborating sources (see note) |
| DOE emergency order in effect | 2026-01-25 – 2026-01-27 | DOE 202(c) filings |
| ERCOT post-event report published | 2026-01-28 | ERCOT (primary) |

> **Provenance note.** ERCOT's post-event report is titled "Winter Storm Fern – January 2026"
> and confirms the Jan 21 Weather Watch, but its three pages do **not** print an explicit
> event date range. The Jan 23–26 range comes from corroborating coverage (which also
> describes the storm as running "Friday through Monday" — Jan 23, 2026 was a Friday) and the
> DOE emergency-order window. Treated as **well-corroborated but not ERCOT-verbatim**; the
> preprint should cite the DOE order dates, which are documentary.

### Window intersections

| Project window | Dates | Intersects Fern? |
|---|---|:--:|
| Bootstrap analog pool | from 2026-01-09, strictly-before-target | **YES** — Fern days are pool members for every panel |
| **W5-A train (τ_p, s_p fitted here)** | **Jan 23 – Apr 13** | **YES — Fern is the first 4 days of the train window** |
| W5-A val | Apr 14 – 19 | no |
| Eval panel | Apr 20 – 26 | no |
| W5-R scarcity-confirmatory | Apr 27 – May 3 | no |
| W5-R calm | May 4 – 10 | no |
| W5-B panels | May 11 – 31 | no |
| W5-R scarcity-primary | Jun 1 – 7 | no |
| W6 July panels | Jun 29 – Aug 2 | no |

### Weight of Fern inside the training window

τ_p is the q90 of realized RT MCPC over the train window, so Fern's share of the
above-threshold mass is the quantity that matters:

| Product | τ_p | Train intervals > τ_p | Of which in Fern | **Fern share** |
|---|---:|---:|---:|---:|
| regup | 3.56 | 1,760 | 571 | **32.4%** |
| rrs | 2.71 | 828 | 22 | 2.7% |
| ecrs | 2.56 | 1,100 | 139 | 12.6% |
| nspin | 14.98 | 762 | 117 | 15.4% |

Fern is **4.9%** of the train window by duration (1,152 of 23,328 intervals).

**Two sentences for the paper.** Winter Storm Fern (Jan 23–26, 2026) sits at the very start of
the W5-A training window — its first day *is* the training window's first day — and Fern days
are members of the bootstrap analog pool for every panel in the project. Although only 4.9% of
the training window by duration, Fern supplies **32.4% of the above-τ_p regup intervals** (and
12–15% for ecrs/nspin) that determine the fitted thresholds, so the frozen correction's trigger
level is materially set by a single named storm — the same single-episode dependence ADR 0015
identified downstream, now shown to be present in the *fitting* data as well.

> No refit was performed. Recomputing τ_p with Fern excluded is a natural sensitivity check but
> is **out of scope here** (it would be a refit); recorded as a recommended follow-up.
