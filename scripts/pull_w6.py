#!/usr/bin/env python3
"""W6-pull — extend the ERCOT backfill from the Jun-9 ceiling through Aug 3, 2026.

Thin wrapper over the proven `pull_w5r` infra (which itself wraps `backfill_w3b`).
Nothing about the fetch/assembly logic changes — only the date window, the months to
reassemble, and the log path. The W5-R-pull binding requirements therefore all carry
over unchanged:

  - completeness-based skip (a PARTIAL cached day is re-pulled, not treated as done),
  - atomic writes (tmp + os.replace),
  - checkpoint log + continue-past-hard-failing-day,
  - >=2s throttle between every request,
  - schema-drift STOP (no silent coercion).

Window: Jun 8 (re-verified for completeness; skipped if already complete) through
Aug 3, 2026 inclusive. That covers every complete July Mon-Sun week from Jun 29-Jul 5
through Jul 27-Aug 2, each with its Sun+1 UTC tail.

Phases:  fetch (default) -> assemble.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pull_w5r as p5  # noqa: E402  proven fetch/assemble/completeness/atomic-write

# ── W6 window overrides (the only deltas from W5-R-pull) ────────────────────────
p5.PULL_START = date(2026, 6, 8)      # re-verify the last cached day, then extend
p5.PULL_END_EXCL = date(2026, 8, 4)   # through Aug 3 inclusive
p5.REPAIR_BEFORE = date(2026, 6, 9)   # schema-reference scan hits the cached Jun 8
p5.ASSEMBLE_MONTHS = ["2026-06", "2026-07", "2026-08"]
p5.LOG_PATH = REPO_ROOT / "data" / "audit" / "w6_pull_log.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="fetch", help="fetch | assemble | fetch,assemble")
    args = ap.parse_args()
    phases = args.phase.split(",")
    print(f"W6-pull window: {p5.PULL_START} -> {p5.PULL_END_EXCL} (excl); "
          f"months={p5.ASSEMBLE_MONTHS}", flush=True)
    if "fetch" in phases:
        p5.run_fetch()
    if "assemble" in phases:
        p5.run_assemble()


if __name__ == "__main__":
    main()
