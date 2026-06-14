> Superseded by results_w5r_run.md / ADR 0013; retained for provenance

# W5-R-ingest — Ingestion Recon (diagnose before pulling)

**Scope:** diagnose coverage + gap structure + threshold-metric feasibility so the real
pull is scoped correctly. **No bulk download, no ingestion.** Recommendation only.
**Method note:** Phase 1/2 live checks used **9 `size=1` head queries** to the ERCOT
Public API (no bulk download). Network reachable; credentials in `~/hybridbid/.env`
valid (token acquired).

---

## Q0 — Threshold-metric feasibility (realized AS effective price > τ_p)

**Confirmed: a one-line threshold swap at W5-R re-run — no reconstruction.**

- "Realized AS effective price" = **realized RT MCPC**. The W4-A E[max] effective
  price is a *forecast* construct, `mean_t E_k[max(scenario+δ, 0)]`; for a *realized*
  value there is no scenario distribution and realized MCPC ≥ 0, so
  `max(realized, 0) = realized`. The realized effective price is just the realized MCPC.
- The count "intervals where realized AS effective price > τ_p" is **already
  implemented** as `scripts/backtest_w5r.py:qualifying_count` (it counts realized RT
  MCPC > threshold). Switching from the recomputed q90-realized thresholds to the
  correction's own **τ_p** is a one-line change: read τ_p from
  `data/audit/w5a_eval.json` (regup 3.56 / rrs 2.71 / ecrs 2.56 / nspin 14.98) and pass
  that dict. Realized MCPC is `ForecasterDataset.get_rt_array(d)[p]`. No reconstruction.
- (If a *forecast*-side E[max] is ever needed, it is `einsum("k,kst->st", probs,
  scenarios)` per `scripts/backtest_w5a_eval.py:_effective_bias_through_forecaster`.)
- **Note for re-run (not re-selected here):** τ_p exceeds the q90-realized thresholds
  for most products (e.g. regup 3.56 vs 2.65), so τ_p-based qualifying counts will be
  *lower* than the W5-R Phase-1 context numbers. Selection is deferred to the re-run.

---

## Phase 1 — ERCOT availability (live, read-only)

All locally-ingested daily series stop **uniformly at 2026-05-10** (raw caches
`~/hybridbid/data/raw/{rt_lmp,dam_as,sced_mcpc,wind,solar}` all end `2026-05-10`).
Live ERCOT head queries (today, June 13):

| Series | Report ID | Local latest | ERCOT available (live) | Classification |
|---|---|---|---|---|
| RT MCPC | NP6-332-CD | 2026-05-10 | **≥ 2026-06-11** (1,440 rec/day) ✓ live-confirmed | **ingestion gap** |
| RT LMP | NP6-788-CD | 2026-05-10 | **≥ 2026-06-11** (319,968 rec/day) ✓ live-confirmed | **ingestion gap** |
| DAM AS | NP4-188-CD¹ | 2026-05-10 | available (day-ahead product; same run) — inferred² | **ingestion gap** |
| Net load | load-forecast-by-model + wind/solar | 2026-05-10 | available (same run) — inferred | **ingestion gap** |

¹ DAM AS is fetched via gridstatus (`get_as_prices`, NP4-188-CD), not a direct URL.
² My direct head query guessed the NP4-33-CD path and got HTTP 404 (wrong endpoint
schema, not an availability signal); DAM is day-ahead (published ~1pm prior day), the
least lag-prone series, and stopped in the same May-10 run.

**Root cause = ingestion failure, not publication lag.** The last backfill
(`scripts/backfill_w3b.py`) was explicitly scoped "**Apr 16 – May 10, 2026**" *and*
its `sced_mcpc/download.log` shows it died on **HTTP 500 + sustained HTTP 429
rate-limiting** (repeated 32 s backoffs on NP6-332-CD). ERCOT publishes all four
series in near-real-time / day-ahead; as of June 13 it has data through ~June 12.

### 60-day disclosure check (explicit)

**No panel input is capped by a 60-day product.** The only 60-day-lagged item in the
lineage is **post-settlement actual load**, and `backfill_w3b.py:fetch_load` (line
~271) *deliberately substitutes* `get_load_forecast_by_model` (InUseFlag, near-real-time)
for recent dates precisely to avoid that ~60-day lag. The `~/hybridbid/data/
ercot_disclosure/{sced,dam}` 60-day SCED/DAM resource data exists but is **not read by
the forecaster price/net-load pipeline** (it serves ASDC / resource-level work). So
there is **no availability ceiling** from a 60-day product.

---

## Phase 2 — Gap-structure forensics (near-miss weeks)

Both near-miss weeks: **scattered, short gaps — not block outages.**

| Week | Series | Missing | Runs | Max run | Concentration |
|---|---|---:|---:|---:|---|
| Apr 27–May 3 | each MCPC | 40 (1.98%) | 22 | **5 intervals (25 min)** | May 1 (30), Apr 30 (7), May 2 (2), Apr 27 (1) |
| Apr 27–May 3 | LMP | 13 (0.64%) | 6 | 4 (20 min) | May 1 (11) |
| May 4–10 | each MCPC | 70 (3.47%) | 38 | **5 intervals (25 min)** | May 5 (31), May 6 (22), May 4 (9), May 7–8 (8) |
| May 4–10 | LMP | 36 (1.79%) | 11 | 5 (25 min) | May 5–6 (25) |

The 5 AS products share an identical gap pattern (whole missing SCED intervals); LMP
gaps fall on different intervals. Largest contiguous gap anywhere is **5 intervals
(25 min)** — no day-scale outage.

**Local vs ERCOT (live cross-check on the gappiest days):**

| Day | Local MCPC intervals | ERCOT records | Verdict |
|---|---|---|---|
| 2026-05-01 | 258 / 288 (30 missing) | 1,440 (= 288 full) | **local-only → re-pullable** |
| 2026-05-05 | 257 / 288 (31 missing) | 1,445 (= 289 full) | **local-only → re-pullable** |
| 2026-05-06 | 266 / 288 (22 missing) | 1,440 (= 288 full) | **local-only → re-pullable** |

ERCOT has **complete** data for every gappy day; the local gaps are download misses
from the rate-limited May-10 backfill. **A clean re-pull recovers them** (the gaps are
not ERCOT-absent).

---

## Phase 3 — Recommendation: **(A) Clean re-pull**

The evidence is unambiguous: ERCOT has complete, clean data well past the local May-10
ceiling; the near-miss-week gaps are local-only and re-pullable; there is no 60-day
ceiling and no publication lag. **(B) interpolation is unnecessary** (gaps are
re-pullable, not ERCOT-absent). **(C) availability ceiling does not apply.**

### Scope for the pull chunk (to be executed separately)

- **Series:** RT MCPC (NP6-332-CD), RT LMP (NP6-788-CD), DAM AS (NP4-188-CD), wind
  (NP4-732-CD), solar (NP4-737-CD), load-forecast (NP3-565-CD) — the existing
  `backfill_w3b.py` set.
- **Date range:** **Apr 27 – Jun 8, 2026** (~43 days). This (a) *repairs* the two
  near-miss weeks (re-pulling May 1 / 5 / 6 etc. fills the scattered local gaps) and
  (b) *extends* coverage to fresh complete weeks **May 11–17, May 18–24, May 25–31,
  Jun 1–7**, each with its required Sun+1 rolling tail (Jun 1–7 needs Jun 8; ERCOT has
  through ~Jun 12).
- **Expected yield:** Apr 27–May 3 (29% qualifying intervals) becomes an eligible
  **scarcity** panel once repaired; the fresh May/June weeks supply candidates for a
  **calm** panel — satisfying the ADR 0012 two-panel requirement (one scarcity + ideally
  one calm).
- **Runtime / risk:** nominal ~1 s/day/series × 6 series × 43 days ≈ 4–5 min, **but the
  last run died on 429 rate-limiting** (32 s backoffs). Budget **20–45 min** and pace
  the pull: ≥2 s/request, exponential backoff, skip-existing/resumable. The 9 live
  probe queries just now all returned HTTP 200 (no 429), so the API is currently
  healthy — the earlier failure was burst-rate, not a hard cap. The pull chunk should
  set conservative throttling to avoid repeating the failure.

---

## Acceptance criteria

- [x] Q0 metric feasibility confirmed (one-line τ_p swap in `qualifying_count`; realized
  MCPC via `get_rt_array`; no reconstruction)
- [x] Phase 1 per-series ERCOT-available-vs-local; ingestion-gap vs publication-lag
  classified (all = ingestion gap; RT MCPC & RT LMP live-confirmed through June 11)
- [x] 60-day disclosure dependency checked — none binding (post-settlement load
  substituted by near-real-time forecast)
- [x] Phase 2 gap structure (scattered, ≤25 min runs) + local-vs-ERCOT (local-only,
  re-pullable) for both near-miss weeks
- [x] Phase 3 single recommendation (A) with evidence and scoped range/runtime
- [x] No bulk download (9 `size=1` head queries only), no ingestion, no merge

**HARD STOP** — the pull (range/throttling) is decided and scoped in chat as a separate chunk.