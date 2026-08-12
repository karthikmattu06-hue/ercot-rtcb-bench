# ADR 0017 — July 2026 seasonal test: mild summer bounds the non-stationarity claim; both sub-claims hold within the bound (W6)

**Status:** Accepted
**Date:** 2026-08-10

---

## Context

ADR 0015 scoped its non-stationarity claims to **7 panels, Apr–Jun 2026, early RTC+B**, and
named summer ERCOT scarcity — a materially different regime — as **unestablished and an open
thread**. W6 was the pre-registered test of that thread.

W6 extended all series from the Jun 9 ceiling through **Aug 3, 2026** (393 files pulled, 0
failed, 0 empty, no schema drift; backup + sha256 manifest taken before reassembly per the
binding rule) and ran a protocol whose three interpretation criteria were **fixed in advance**
of any result. The frozen ADR 0012 parameters were asserted equal at runtime; no refit was
performed.

Integrity gates all passed: 5 of 5 candidate July weeks eligible (worst-series gap
0.000–0.099%, gate ≤0.5%), and the no-regression check reproduced the ADR 0013 canonical eval
baseline at **$238,378.80229** (drift +$0.00229, tolerance ±$1.00).

Full detail: `docs/results_w6_seasonal.md`, `data/audit/w6_seasonal.json`.

### Epistemic labels used below

- **CONFIRMED** — supported by pre-registered evidence within the stated window.
- **CANDIDATE** — a mechanism consistent with observation but not separated from confounds.
- **NOT ESTABLISHED** — proposed, tested, and *not* supported by the evidence gathered.

---

## Decision — what W6 establishes

### 1. Criterion 3 (null) FIRES — this is the binding result

July 2026 was **mild**. τ_p-qualifying counts for the five candidate July weeks were
**6, 20, 20, 27, 221** against a spring range of **187–376**. The most-scarce July week
(Jul 20–26, 221) sits *mid-spring-range* and **below both spring scarcity panels** (341, 376)
used in W5-R.

The severe-summer regime **did not occur in the observed window**. W6 therefore **bounds**
ADR 0015's scope rather than testing it at the intended severity. Seasonal-generalisation
statements remain scoped to observed weeks; the summer test ADR 0015 asked for has **not**
been answered.

### 2. Criterion 1 — evening-peak LMP bias instability: **CONFIRMED (within the bound)**

Extending the per-week table to 12 panels: the sign keeps flipping into summer
(**2 negative / 3 positive**), and the cross-panel mean stays at zero —
**+$0.86/MWh, median −$0.04** over all 12 panels (summer-only mean +$3.21).

Summer magnitudes are far tighter (**−$3.18 to +$15.13**) than spring's (−$48.01 to +$30.02);
no July week contains an Apr-25 analogue. The COMPLICATES branch — a stable, same-sign summer
bias of consistent magnitude — is **not** triggered.

### 3. Criterion 2 — AS lever, no stable edge: **CONFIRMED (within the bound)**

Only **one** summer panel carried enough scarcity to constitute a test.

- **Summer scarcity (Jul 20–26, 221 qualifying):** frozen lever **+$5,483.04** (+18.7% of PF
  headroom), E and AS both up. But **single-day concentrated** — Jul 23 alone (+$5,760)
  **exceeds the panel net** — with a losing day (Jul 21, −$795). The gain does **not track
  scarcity intensity**: the most-scarce day (Jul 22, 81 qualifying) returned only +$210.
- **Summer calm (Jul 13–19, 6 qualifying):** **exactly $0.00** on all seven days. The lever
  was **inert, not merely small** — the DAM quote never crossed τ_p, so the two-regime rule
  never fired. This differs from the May 4–10 spring calm week (−$10,619), where it fired and
  lost.

COMPLICATES required consistent wins *across* summer scarcity panels. There was one, and its
win reproduces the same concentration signature that sank the lever in W5-R.

**Explicitly: this is NOT grounds to un-retire the lever. ADR 0014 stands.**

### 4. Maturation mechanism — **NOT ESTABLISHED** (proposed, tested, unsupported)

W6 proposed that DAM AS quote levels settling post-go-live might dissolve the correction's
trigger condition — a second non-stationarity mechanism distinct from scarcity realization —
and Exhibit 1 was built to test it by tracking the fraction of DAM AS quotes exceeding the
frozen τ_p, per product, per month (Jan–Jul 2026).

**The series does not decline monotonically.** For regup: 17.9 → 5.1 → 2.8 → **13.5 → 10.7**
→ 4.2 → 1.8 (%). It falls Jan→Mar, **rebounds sharply Apr–May**, then falls Jun→Jul. July is
the series minimum for regup and rrs but **not** for ecrs (Mar) or nspin (Feb).

**The trend is confounded with scarcity.** The DAM crossing fraction co-moves with realized
scarcity month by month (e.g. Apr: DAM 13.5% / realized 8.7%; Jun: 4.2% / 9.1%), so calendar
time and market conditions are not separable in this exhibit. The Apr–May rebound tracks the
spring scarcity months, not a maturation path. Establishing maturation would require a
**scarcity-normalised** measure that W6 does not provide.

What Exhibit 1 **does** establish is narrower and still useful: the trigger condition is
**strongly time-varying** (regup 1.8%–17.9% across seven months), which is sufficient on its
own to explain the Jul 13–19 inertness without invoking maturation.

> Recorded honestly as a negative: the mechanism was hypothesised, tested, and not supported.
> The external corroboration anticipated for the preprint (IMM nspin over-procurement
> reporting; market-analytics commentary on early-period elevated DAM AS) was **not verified
> in W6** and must be sourced and checked before any citation — it cannot be leaned on to
> rescue a mechanism this repo's own data does not show.

### 5. Winter Storm Fern sits inside the training window — disclosure

**Winter Storm Fern: ~Jan 23–26, 2026** (ERCOT Weather Watch Jan 21; DOE emergency order
Jan 25–27; ERCOT post-event report published Jan 28). ERCOT's report confirms the event and
the Weather Watch but prints no explicit date range; the Jan 23–26 window is well-corroborated
rather than ERCOT-verbatim, and the preprint should cite the documentary DOE order dates.

| Window | Dates | Intersects Fern? |
|---|---|:--:|
| Bootstrap analog pool | from 2026-01-09 | **YES** — pool member for every panel |
| **W5-A train (τ_p, s_p fitted here)** | **Jan 23 – Apr 13** | **YES — Fern is its first 4 days** |
| W5-A val / eval / all W5-R, W5-B, W6 panels | Apr 14 onward | no |

Fern is **4.9%** of the training window by duration but supplies **32.4% of the above-τ_p
regup intervals** (ecrs 12.6%, nspin 15.4%, rrs 2.7%) that determine the fitted thresholds.

**The frozen correction's trigger level is materially set by a single named storm.** This is
the same single-episode dependence ADR 0015 identified *downstream* in the evaluation panels,
now shown to be present in the *fitting* data as well. It strengthens the ADR 0015 conclusion
and must be disclosed in the paper.

### 6. Data-vintage note

The Jun 1–7 evening-peak bias moved **−16.17 → −16.15** ($0.02, ~0.1%) after the June parquet
was reassembled; the other six spring panels reproduce to the cent. No sign, ordering, or
finding changes. Flagged **forward-only** per the ADR 0013 precedent; the eval-panel
no-regression gate is the binding check and it passed. Backup rule followed (pre-assembly
sha256 manifest + copy at `~/ercot-w6-backup-preassemble/`).

---

## Consequences

- ADR 0015 stands, with its scope now **explicitly bounded**: tested against Apr–Jun 2026
  *and* a mild Jul 2026, not against a severe summer.
- ADR 0014 stands. The lever remains retired.
- The maturation mechanism is **not** added to the roadmap as a supported finding.
- The paper gains a required disclosure (Fern in the training window) that it did not
  previously carry.

## Open threads

1. **Severe-summer test — still open and pre-registered.** July did not supply a
   high-scarcity week. August (RT/DAM finite to Aug 4) and September are the natural window.
   The paper states this as ongoing work, not as a settled result.
2. **τ_p sensitivity excluding Fern — new, recommended.** Given Fern's 32.4% share of the
   above-τ regup mass, recomputing the thresholds with Fern excluded is the natural
   robustness check. Deliberately **not** performed in W6 (it would be a refit); recorded as
   scoped follow-up work.
3. **Maturation, if pursued** — requires a scarcity-normalised measure to separate calendar
   time from market conditions.
4. **nspin anchor thread** — unchanged from ADR 0012. Note that the external corroboration
   previously expected here is **unverified**; it must be checked before citation.
