# W5-B Precheck — Evening-Peak LMP Bias Stability (go/no-go)

**Recommendation: NO-GO.** The evening-peak LMP bias **flips sign across panels** and is
**one-day-driven within every panel** — the exact failure mode that sank the AS lever
(ADR 0014). A static evening-peak LMP correction is dead on arrival. The precheck did
its job: it caught this **before** any fix was built.

**Diagnostic only** — no fix, no correction, no intervention LP.

---

## Bias definition (verbatim from W4-A / ADR 0010)

- **Window:** evening peak = **HoD 0 and 1 UTC** (7–8 pm CDT) = the first 24 five-min
  intervals of each UTC day (HoD0 = 0–11, HoD1 = 12–23). 2 HoD × 7 days = 14 operating
  hours / 168 intervals per panel.
- **Bias:** forecast LMP − realized LMP over those intervals. `bias < 0` = under-forecast
  (the W4-A eval sign). Forecast LMP = probability-weighted scenario mean of series 0 —
  which **is** the LP's stage-2 LMP planning quantity (LMP has no non-negativity/E[max]
  clip), so the raw mean bias and the revenue-relevant planning-quantity bias **coincide**.
- **Cross-check (exact):** eval HoD0 mean **−48.77** (W4-A −48.77), HoD1 **−47.25**
  (W4-A −47.25) — reproduces ADR 0010 to the cent, and re-confirms LMP is unchanged by
  the ADR 0013 re-pin.

---

## Per-panel evening-peak bias (7 panels, re-pinned canonical data)

| Panel | bias $/MWh | sign | n | within-σ | day-σ | days sharing panel sign |
|---|---:|:--:|---:|---:|---:|---:|
| eval (Apr 20–26) | **−48.01** | − | 168 | 176.0 | 135.0 | 4/7 |
| Apr 27–May 3 (scar-conf) | **+30.02** | + | 168 | 70.6 | 53.2 | 5/7 |
| May 4–10 (calm) | **+18.94** | + | 168 | 19.3 | 14.2 | 6/7 |
| May 11–17 | **+14.70** | + | 168 | 30.1 | 24.8 | 5/7 |
| May 18–24 | −1.31 | − | 168 | 27.5 | 22.1 | 4/7 |
| May 25–31 | −3.94 | − | 168 | 36.3 | 34.4 | 4/7 |
| Jun 1–7 (scar-primary) | **−16.17** | − | 168 | 24.5 | 21.6 | 5/7 |

### Per-day biases ($/MWh) — one-day-driven within every panel

| Panel | day1 | day2 | day3 | day4 | day5 | day6 | day7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| eval | −9 | −14 | +24 | −1 | +16 | **−377** | +25 |
| Apr 27–May 3 | +31 | −0 | **+140** | +11 | −47 | +24 | +51 |
| May 4–10 | +5 | −3 | +27 | +15 | +17 | +42 | +30 |
| May 11–17 | +11 | +60 | +12 | −22 | −10 | +31 | +20 |
| May 18–24 | −22 | −27 | −24 | +27 | −5 | +24 | +17 |
| May 25–31 | +11 | −5 | **−75** | −19 | +34 | +32 | −6 |
| Jun 1–7 | −44 | +16 | −3 | +3 | −43 | −11 | −31 |

**The eval panel's −$48 is one day: Apr 25 = −$377** (the same scarcity day that drove
the W5-A AS result). The other six eval days are mixed (+24/+16/+25 vs −9/−14/−1). Every
panel is dominated by one or two days with ±$40–377 swings, and per-day signs flip
constantly (only 4–6 of 7 days share each panel's sign).

---

## Cross-panel stability metrics

1. **Sign stability:** **4/7 negative (W4-A sign), 3/7 positive → 3 sign-flips.** The
   bias direction is *not* stable. The eval panel (−$48) and the *adjacent* week
   Apr 27–May 3 (+$30) have large, **opposite-sign** biases.
2. **Magnitude:** min −48.01 · median −1.31 · max +30.02 · **mean −0.82** · CV 29.2. The
   cross-panel mean is essentially **zero** with ±$30–48 swings — there is no stable
   directional bias to target.
3. **Within-window concentration:** every panel is **one-or-two-day-driven** (eval =
   Apr 25 −$377 alone; Apr 27–May 3 = Apr 29 +$140 alone; May 25–31 = May 27 −$75), and
   intra-panel sign agreement is only 4–6/7 days — the same one-day-driven fragility that
   sank AS, now confirmed on the LMP side too.

---

## Recommendation — **NO-GO**

Per the pre-registered mapping, **sign flips across panels → NO-GO.** A static
evening-peak LMP fix is dead on arrival: it would "correct" the eval's −$48 (itself a
single Apr-25 spike) and thereby **hurt** on the +$30/+$19/+$15 over-forecast weeks. This
is structurally identical to the retired AS lever (ADR 0014) — a concentrated bias whose
realization is week-to-week unstable, here flipping even in **sign**. The W4-A eval −$48
"evening-peak underestimation episode" is exactly the unrepresentative single-panel
artifact that ADR 0010 itself flagged as a panel-sensitivity caveat.

**Pivot options (for chat):**
- **(a) Conditional / state-dependent correction** — only a fix that conditions on
  whether the evening-peak scarcity *realizes* could have a stable edge; this is a
  forecasting (EVPI-adjacent) problem, not a static post-hoc bias shift.
- **(b) Retire W5-B** and document as a **second negative result**, alongside W5-R/AS —
  the honest pattern is now clear: the v0.1 forecaster's largest measured biases are
  **scarcity-episode artifacts**, not stable, statically-correctable errors.

The precheck cost one diagnostic run and **saved an entire fix arc** — validating the
replication-native precheck discipline mandated in ADR 0014.

**Files:** `scripts/diagnose_w5b_precheck.py`, audit `data/audit/w5b_precheck.json`.

**HARD STOP** — go/no-go decision and any W5-B scoping happen in chat.
