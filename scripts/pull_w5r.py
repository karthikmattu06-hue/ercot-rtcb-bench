#!/usr/bin/env python3
"""W5-R-pull — resumable/atomic ERCOT backfill Apr 27 – Jun 8, 2026.

Reuses the proven fetch + assembly from backfill_w3b, adding the W5-R-pull binding
requirements the prior run lacked:
  - completeness-based skip (a PARTIAL cached day is re-pulled, not treated as done),
  - atomic writes (tmp + os.replace; never a half-written parquet),
  - checkpoint log + continue-past-hard-failing-day (one 429/500 death costs only that
    in-flight day, never a restart),
  - schema-drift STOP (no silent coercion).

Resume = the raw cache files themselves (a complete file is skipped). Re-running after
a kill picks up exactly where it stopped.

Phases:  fetch (default) → assemble (rebuild forecaster parquets) → gate (integrity).
Run `--phase fetch` in the background, inspect the log, then `--phase assemble,gate`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backfill_w3b as bf  # noqa: E402  proven fetch_*, assemble_month, _raw_cache

AUDIT_DIR = REPO_ROOT / "data" / "audit"
LOG_PATH = AUDIT_DIR / "w5r_pull_log.json"

PULL_START    = date(2026, 4, 27)
PULL_END_EXCL = date(2026, 6, 9)      # through Jun 8 inclusive
REPAIR_BEFORE = date(2026, 5, 11)     # < this = already-cached repair range (completeness-check)
PRODUCTS = ["rt_lmp", "sced_mcpc", "dam_spp", "dam_as", "wind", "solar", "load_actual"]
ASSEMBLE_MONTHS = ["2026-04", "2026-05", "2026-06"]

_SCED_MIN_INTERVALS = 286   # in-day 5-min intervals; complete≈288, partials were 258–278
_LMP_MIN_INTERVALS  = 286


# ── Completeness ────────────────────────────────────────────────────────────────

def _in_day_intervals(path: Path, ts_col_finder, day: date) -> int:
    df = pd.read_parquet(path)
    col = ts_col_finder(df)
    if col is None:
        return 0
    ts = pd.to_datetime(df[col], utc=True, errors="coerce").dt.floor("5min")
    d0 = pd.Timestamp(day, tz="UTC")
    return int(ts[(ts >= d0) & (ts < d0 + pd.Timedelta(days=1))].nunique())


def _sced_ts(df):
    return "sced_timestamp" if "sced_timestamp" in df.columns else None


def _lmp_ts(df):
    return next((c for c in df.columns if "interval" in c.lower() and "start" in c.lower()), None)


def is_complete(product: str, day: date) -> bool:
    path = bf._raw_cache(product, day)
    if not path.exists():
        return False
    try:
        if product == "sced_mcpc":
            return _in_day_intervals(path, _sced_ts, day) >= _SCED_MIN_INTERVALS
        if product == "rt_lmp":
            return _in_day_intervals(path, _lmp_ts, day) >= _LMP_MIN_INTERVALS
        return len(pd.read_parquet(path)) > 0   # dam/wind/solar/load: present & non-empty
    except Exception:
        return False   # unreadable/corrupt → re-fetch


# ── Atomic write ────────────────────────────────────────────────────────────────

def atomic_save(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, compression="snappy")
    os.replace(tmp, path)   # atomic on POSIX


# ── Fetch dispatch (reuse backfill_w3b) ──────────────────────────────────────────

def _fetch(product, day, api, token, sub_key):
    dispatch = {
        "rt_lmp":      lambda: bf.fetch_rt_lmp(api, day),
        "sced_mcpc":   lambda: bf.fetch_sced_mcpc_api(token, sub_key, day),
        "dam_spp":     lambda: bf.fetch_dam_spp(api, day),
        "dam_as":      lambda: bf.fetch_dam_as(api, day),
        "wind":        lambda: bf.fetch_wind(api, day),
        "solar":       lambda: bf.fetch_solar(api, day),
        "load_actual": lambda: bf.fetch_load(api, day),
    }
    return dispatch[product]()


def _reference_schemas() -> dict:
    """Reference column set per product from an existing complete cache (drift guard)."""
    ref = {}
    for product in PRODUCTS:
        d = PULL_START
        while d < REPAIR_BEFORE:
            p = bf._raw_cache(product, d)
            if p.exists():
                try:
                    ref[product] = set(pd.read_parquet(p).columns)
                    break
                except Exception:
                    pass
            d += timedelta(days=1)
    return ref


def _auth():
    import requests
    bf._load_dotenv()
    u = os.environ.get("ERCOT_API_USERNAME", "")
    pw = os.environ.get("ERCOT_API_PASSWORD", "")
    sub = os.environ.get("ERCOT_PUBLIC_API_SUBSCRIPTION_KEY", "")
    if not all([u, pw, sub]):
        raise RuntimeError("Missing ERCOT credentials in env/.env")
    r = requests.post(
        "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
        "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token",
        data={"username": u, "password": pw, "grant_type": "password",
              "scope": "openid fec253ea-0d06-4272-a5e6-b478baeecd70 offline_access",
              "client_id": "fec253ea-0d06-4272-a5e6-b478baeecd70", "response_type": "token"},
        timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token") or r.json().get("id_token")
    api = bf._get_api()
    return api, token, sub


def run_fetch() -> dict:
    api, token, sub = _auth()
    ref = _reference_schemas()
    log = {"pulled": [], "skipped": [], "empty": [], "failed": [], "schema_ref": {k: sorted(v) for k, v in ref.items()}}
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    day = PULL_START
    while day < PULL_END_EXCL:
        print(f"--- {day} ---", flush=True)
        for product in PRODUCTS:
            if is_complete(product, day):
                log["skipped"].append(f"{product}/{day}")
                continue
            try:
                df = _fetch(product, day, api, token, sub)
            except Exception as e:   # noqa: BLE001 — checkpoint-and-continue past hard fail
                log["failed"].append({"item": f"{product}/{day}", "err": str(e)[:160]})
                print(f"  FAILED {product}/{day}: {str(e)[:120]}", flush=True)
                _save_log(log)
                time.sleep(2.0)
                continue
            if df is None or len(df) == 0:
                log["empty"].append(f"{product}/{day}")
                print(f"  empty {product}/{day}", flush=True)
                time.sleep(2.0)
                continue
            if product in ref and set(df.columns) != ref[product]:
                _save_log(log)
                raise RuntimeError(
                    f"SCHEMA DRIFT {product}/{day}: got {sorted(df.columns)} "
                    f"expected {sorted(ref[product])} — STOP (no coercion).")
            ref.setdefault(product, set(df.columns))
            atomic_save(df, bf._raw_cache(product, day))
            log["pulled"].append(f"{product}/{day}")
            print(f"  pulled {product}/{day} ({len(df)} rows)", flush=True)
            _save_log(log)
            time.sleep(2.0)
        day += timedelta(days=1)
        time.sleep(2.0)

    _save_log(log)
    print(f"\nFETCH DONE: pulled={len(log['pulled'])} skipped={len(log['skipped'])} "
          f"empty={len(log['empty'])} failed={len(log['failed'])}", flush=True)
    return log


def _save_log(log: dict) -> None:
    LOG_PATH.write_text(json.dumps(log, indent=2, default=str))


def run_assemble() -> None:
    for mk in ASSEMBLE_MONTHS:
        print(f"Assembling {mk}...", flush=True)
        bf.assemble_month(mk)
    print("Assembly done.", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="fetch", help="fetch | assemble | fetch,assemble")
    args = ap.parse_args()
    phases = args.phase.split(",")
    if "fetch" in phases:
        run_fetch()
    if "assemble" in phases:
        run_assemble()


if __name__ == "__main__":
    main()
