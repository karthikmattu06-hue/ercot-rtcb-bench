# ADR 0015 — v0.1 forecaster bias is non-stationary; static bias correction is not bankable (W5 consolidated)

**Status:** Accepted (consolidated negative result)
**Date:** 2026-06-14

---

## Context

W4 measured the two largest BESS-revenue levers as single-panel (Apr 20–26) *oracle
bounds*: the AS effective-price error ($36,393; ADR 0010) and the LMP evening-peak mean
bias (ΔLMP ≈ $21,500; ADR 0010/0011). W5 attempted to bank them:

- **AS:** W5-A built a scarcity-conditioned DAM-anchor shrinkage (ADR 0012) — 50.2%
  recovery on the single eval panel. W5-R replication (ADR 0013 data adoption; 3 new
  pre-registered panels, frozen parameters) **retired it** (ADR 0014).
- **LMP:** the W5-B precheck — a 7-panel evening-peak bias-stability diagnostic run
  *before* building any fix — returned **NO-GO** (`docs/results_w5b_precheck.md`).

This ADR consolidates both outcomes under one mechanism and reframes the v0.2 program.
It supersedes the piecemeal ordering of ADRs 0012/0014; the prior ADR bodies are left
unedited (forward-only, per the ADR 0013 precedent).

## Finding (the contribution)

**The v0.1 forecaster's two largest measured biases are non-stationary
scarcity-episode artifacts, not statically correctable errors** — shown by the same
mechanism on both:

- **AS (ADR 0014):** the frozen shrinkage lost on 2 of 3 new panels, including the
  *most-scarce* week; Δ>0 vs Δ<0 panels split by whether the forecast AS scarcity
  actually *realized* in RT (Δ<0 panels show energy *and* AS both falling — the shrink
  under-commits AS when scarcity is real); every panel's net is one-or-two-day-driven.
- **LMP (W5-B precheck):** the evening-peak bias **sign-flips** across the 7 panels
  (4 negative / 3 positive), cross-panel mean ≈ **0** (−$0.82/MWh) with CV ≈ 29 and
  ±$30–48 swings. The eval panel's −$48/MWh is a **single Apr-25 spike** (−$377 that
  day) — **the same scarcity day** that drove the AS lever.
- **Common root:** W4's single eval panel (Apr 20–26) contained Apr 25, a scarcity day;
  both oracle bounds were largely that one day's signature. A static correction of a
  non-stationary, scarcity-realization-dependent bias is a **directional bet that wins
  or loses by whether scarcity realizes** — no stable edge across panels.

This is the **same claim as the W4-B residual decomposition** (ADR 0011): the ~$51.6k
CF-AB→PF remainder was characterized as distribution-realism + value-of-information that
an unconditional correction cannot reach. W5 demonstrates it **from the fix side**:
recoverable headroom ≪ the oracle bounds, because the bounds are **EVPI-dominated, not
bias-dominated** — the gap is mostly the value of *knowing whether scarcity will
realize*, which no post-hoc bias shift provides.

## Decision

- **Retire W5-B** — no static LMP evening-peak fix is built. This is the second
  documented negative result, with the same mechanism as ADR 0014.
- **Retain both diagnostics in full:** the W5-A Phase-1 AS over-forecast measurement
  (`results_w5a_diagnostic.md`) and the W4-A ΔLMP evening-peak measurement (ADR 0010).
  The measurements stand; the static fixes do not.
- **Reframe the v0.2 forecaster program.** The goal is **scarcity-realization
  conditioning** — a forecasting problem (predict *whether* the evening/AS scarcity
  materializes), **not** post-hoc bias shifts. The previously-"deferred" conditional /
  state-dependent correction is not a pivot declined; it is the correctly-scoped version
  of the entire forecaster-improvement effort.

## Scope of the claim (calibration — binding)

The non-stationarity finding is supported **within the observed window only: 7 panels,
Apr–Jun 2026, early RTC+B.** Seasonal generalization — in particular summer ERCOT
scarcity, a materially different regime — is **unestablished and named as an open
thread.** The claim is not to be stated past this evidence.

## v0.2 work ordering (forward note; supersedes ADR 0011/0012/0014 ordering, bodies unedited)

- **AS effective-price lever** — bound measured ($36.4k), fix retired (ADR 0014). Not banked.
- **LMP evening-peak lever** — bound measured (~$21.5k), fix NO-GO (this ADR). Not banked.
- **LMP spread narrowing ($5.9k), AS scenario-family change, LMP distribution realism**
  — unchanged from ADR 0011 but **reframed**: all are facets of distribution / scarcity
  realism, which is the v0.2 forecasting target.
- **v0.2 = scarcity-realization conditioning, not bias correction.**

## Open threads

- **Conditional correction (v0.2 direction):** scope as a forecasting-research effort
  (predict scarcity realization, condition the forecast/dispatch on it) — *not* a quick
  post-hoc chunk. Design TBD.
- **Seasonal generalization:** test the non-stationarity claim on a summer panel once
  data exists (coverage currently ~Jun 9).
- **nspin anchor over-quote** (ADR 0012): unchanged.
- **Blog #2 / preprint:** lead with the consolidated negative result and the
  methodology claim — *single-panel BESS-bidding backtests overstate gains; two top
  levers evaporate under pre-registered multi-panel replication.* Supersedes all prior
  "found a lever" framings.
- **Zenodo v0.2 re-deposit** (ADR 0013 carry): still a preprint-reproducibility
  prerequisite (adopted canonical data postdates the public v0.1 deposit).
