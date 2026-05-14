#!/usr/bin/env bash
# Reproduce the v0.1 dataset from ERCOT public APIs.
#
# v0.1 covers Dec 5, 2025 – Mar 31, 2026 (post-RTC+B launch through end of Q1).
# Most of this data is already in ~/hybridbid/data/raw/. This script will
# skip cached files and only fetch what is missing.
#
# Usage:
#   bash scripts/fetch_v0_1.sh
#
# After fetching, build the canonical Parquet tables:
#   python scripts/build_v0_1.py

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START="2025-12-05"
END="2026-04-01"   # exclusive

echo "[fetch_v0_1] Fetching ${START} to ${END} (exclusive)"
bash "${REPO_ROOT}/scripts/fetch_v1_0.sh" "${START}" "${END}"
echo "[fetch_v0_1] Done. Run 'python scripts/build_v0_1.py' to build canonical tables."
