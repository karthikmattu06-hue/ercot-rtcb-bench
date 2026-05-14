#!/usr/bin/env bash
# Fetch data for the v1.0 backfill: April 1, 2026 – June 5, 2026.
#
# Usage:
#   bash scripts/fetch_v1_0.sh                    # full backfill (Apr 1 – Jun 5, 2026)
#   bash scripts/fetch_v1_0.sh 2026-04-01 2026-04-04   # test window (3 days)
#
# Requires:
#   - Python env with ercot-rtcb-bench[fetch] installed
#   - .env file with ERCOT_API_USERNAME, ERCOT_API_PASSWORD,
#     ERCOT_PUBLIC_API_SUBSCRIPTION_KEY
#   - HYBRIDBID_DIR env var (default: ~/hybridbid)
#
# Output:
#   Writes raw Parquet files to $HYBRIDBID_DIR/data/raw/<product>/<date>.parquet
#   (same layout as the existing HybridBid raw cache, for consistency).
#   Writes fetch log to data/audit/v1_0_fetch_log.json.
#
# Rate-limit note:
#   The ERCOT API enforces ~10 req/min per endpoint. The Python fetcher
#   uses 2s sleep between requests + exponential backoff on 429s.
#   Do NOT parallelize product fetches — the shared API key is rate-limited.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${REPO_ROOT}/data/audit"
mkdir -p "${LOG_DIR}"

START="${1:-2026-04-01}"
END="${2:-2026-06-06}"   # exclusive; Jun 5 inclusive = Jun 6 exclusive

echo "[fetch_v1_0] Fetching ${START} to ${END} (exclusive)"
echo "[fetch_v1_0] Log: ${LOG_DIR}/v1_0_fetch_log.json"

# Load .env if present
if [ -f "${REPO_ROOT}/.env" ]; then
    set -a
    source "${REPO_ROOT}/.env"
    set +a
    echo "[fetch_v1_0] Loaded .env"
fi

# Check credentials
for var in ERCOT_API_USERNAME ERCOT_API_PASSWORD ERCOT_PUBLIC_API_SUBSCRIPTION_KEY; do
    if [ -z "${!var:-}" ]; then
        echo "[fetch_v1_0] ERROR: ${var} not set. Add it to .env" >&2
        exit 1
    fi
done

python3 - <<PYEOF
import json
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fetch_v1_0")

sys.path.insert(0, str(Path("${REPO_ROOT}") / "src"))
from ercot_rtcb_bench.data.fetch import fetch_and_cache

HYBRIDBID_DIR = Path(os.environ.get("HYBRIDBID_DIR", Path.home() / "hybridbid"))
RAW_DIR = HYBRIDBID_DIR / "data" / "raw"
START = "${START}"
END = "${END}"

# Products to backfill (sced_mcpc must be downloaded separately from ERCOT's
# MISAPP portal — it is not available via the public ErcotAPI)
PRODUCTS = [
    {"name": "rt_lmp", "kwargs": {"location": "HB_HUBAVG"}},
    {"name": "dam_as", "kwargs": {}},
    {"name": "load_actual", "kwargs": {}},
    {"name": "load_forecast", "kwargs": {}},
    {"name": "wind", "kwargs": {}},
    {"name": "solar", "kwargs": {}},
]

log = {
    "version": "v1.0",
    "fetch_start": datetime.utcnow().isoformat() + "Z",
    "date_range": {"start": START, "end": END},
    "products": {},
}

all_ok = True
for spec in PRODUCTS:
    product = spec["name"]
    logger.info("=== Fetching %s (%s to %s) ===", product, START, END)
    try:
        results = fetch_and_cache(
            product=product,
            start=START,
            end=END,
            raw_dir=RAW_DIR,
            **spec["kwargs"],
        )
        n_ok = sum(v for v in results.values())
        n_fail = len(results) - n_ok
        log["products"][product] = {
            "days_ok": n_ok,
            "days_failed": n_fail,
            "failures": [d for d, ok in results.items() if not ok],
        }
        if n_fail > 0:
            logger.warning("%s: %d/%d days failed", product, n_fail, len(results))
            all_ok = False
        else:
            logger.info("%s: %d/%d days OK", product, n_ok, len(results))
    except Exception as e:
        logger.error("%s: fetch crashed: %s", product, e)
        log["products"][product] = {"error": str(e)}
        all_ok = False

log["fetch_end"] = datetime.utcnow().isoformat() + "Z"
log["overall_ok"] = all_ok

out = Path("${LOG_DIR}") / "v1_0_fetch_log.json"
out.write_text(json.dumps(log, indent=2))
logger.info("Fetch log: %s", out)

if not all_ok:
    logger.error("Some fetches failed. Check log for details.")
    sys.exit(1)
logger.info("All fetches complete.")
PYEOF

echo "[fetch_v1_0] Done. Log: ${LOG_DIR}/v1_0_fetch_log.json"
