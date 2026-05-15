# Cleanup log for 01-rtcb-walkthrough.md

## Summary
- Applied: 1 change
- Preserved as-is: 0 items
- Flagged for Karthik: 2 items
- **Net assessment:** Post improved (marginally) — the post was already clean. One unearned bold removed. Ship the revised version.

---

## Applied changes

### Change 1
- **Line:** ~36
- **Category:** Unearned bold
- **Before:** `**SCED now co-optimizes energy and ancillary services jointly, with explicit BESS state-of-charge tracking.**`
- **After:** `SCED now co-optimizes energy and ancillary services jointly, with explicit BESS state-of-charge tracking.`
- **Rationale:** Bolding an entire load-bearing sentence is not a definition or heading. The surrounding prose already signals this is the key claim (it follows "The core change is..."); the bold is redundant and reads as emphasis-inflation.

---

## Flagged for Karthik's judgment

### Flag 1 — Awkward gerund list (line ~131)
- **Original:** `The first month of RTC+B was characterized by operators learning — and ERCOT's algorithm calibrating.`
- **Issue:** "Was characterized by [operators learning] — and [ERCOT's algorithm calibrating]" is grammatically valid but the em-dash before "and" creates an odd parallel gerund list. "Characterized by" also reads slightly passive/formal here.
- **Possible rewrite:** `The first month of RTC+B was an adjustment period — operators still learning the market, ERCOT's algorithm still calibrating.`
- **Recommendation:** Take or leave. The rewrite is marginally cleaner but the original is not wrong. Your call.

### Flag 2 — Figure placeholder (lines ~175–177)
- **Original:**
  ```
  *(Figure: 4-panel time series plot — rt_mcpc for each AS product, Jan 2026.
  Generated in notebooks/exploratory/. Will be embedded here before publication.)*
  ```
- **Issue:** This is a content gate, not a style issue. The post currently has a visible placeholder note that will appear in the Substack editor. You have two options before publishing:
  1. **Generate and embed the figure.** Notebook is in `notebooks/exploratory/`. Substack accepts images in the editor.
  2. **Delete the placeholder and ship without the figure.** The prose before and after the figure section stands on its own. The next post can introduce figures properly.
- **Recommendation:** Delete the placeholder and ship without the figure. The four "Why This Is Hard" asymmetries are the post's actual value; the figure is decorative here. You can add figures to a future revision or embed them in post #2 where they carry more analytical weight.

---

## What was NOT changed

The post is notably clean for a technical blog draft. No filler transitions ("It's worth noting", "Importantly", "Furthermore"), no hedging clusters, no opening flourishes, no closing summaries. The four-section "Why This Is Hard" structure uses parallel headings intentionally — that parallelism is load-bearing for scanning and was left alone.
