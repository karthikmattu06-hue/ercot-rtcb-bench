#!/usr/bin/env python3
"""Audit script: produce a manifest of the HybridBid source data for v0.1.

Reads ~/hybridbid/data/raw/ and ~/hybridbid/data/processed/ (read-only).
Writes:
    data/audit/v0_1_manifest.json
    data/audit/v0_1_manifest.md

Run from the repo root:
    python scripts/audit_v0_1.py
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HYBRIDBID_DIR = Path(os.environ.get("HYBRIDBID_DIR", Path.home() / "hybridbid"))
REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

RAW_DIR = HYBRIDBID_DIR / "data" / "raw"
PROCESSED_DIR = HYBRIDBID_DIR / "data" / "processed"

RAW_PRODUCTS = [
    "rt_lmp_5min", "dam_as", "dam_spp", "sced_mcpc",
    "load_actual", "load_forecast", "wind", "solar",
]
PROCESSED_TABLES = ["as_prices", "energy_prices", "system_conditions"]


def audit_raw_product(product: str) -> dict:
    product_dir = RAW_DIR / product
    if not product_dir.exists():
        return {"exists": False}

    files = sorted([f for f in product_dir.glob("*.parquet")])
    if not files:
        return {"exists": True, "file_count": 0}

    total_bytes = sum(f.stat().st_size for f in files)
    dates = [f.stem for f in files]

    # Sample schema from first and last file
    schema_info: dict = {}
    for path in [files[0], files[-1]]:
        try:
            df = pd.read_parquet(path)
            schema_info[path.stem] = {
                "shape": list(df.shape),
                "columns": list(df.columns),
            }
        except Exception as e:
            schema_info[path.stem] = {"error": str(e)}

    # Gap detection
    try:
        date_index = pd.DatetimeIndex(pd.to_datetime(dates))
        full_range = pd.date_range(date_index.min(), date_index.max(), freq="D")
        missing = [d.strftime("%Y-%m-%d") for d in full_range if d not in date_index]
    except Exception:
        missing = []

    return {
        "exists": True,
        "file_count": len(files),
        "date_first": dates[0],
        "date_last": dates[-1],
        "size_mb": round(total_bytes / 1_048_576, 1),
        "schema_sample": schema_info,
        "missing_dates": missing[:20],  # cap at 20
        "missing_count": len(missing),
    }


def audit_processed_table(table: str) -> dict:
    table_dir = PROCESSED_DIR / table
    if not table_dir.exists():
        return {"exists": False}

    files = sorted(table_dir.glob("*.parquet"))
    if not files:
        return {"exists": True, "file_count": 0}

    total_bytes = sum(f.stat().st_size for f in files)
    month_summaries = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            is_post = df.get("is_post_rtcb", pd.Series([False])).sum()
            month_summaries.append({
                "month": f.stem,
                "rows": len(df),
                "columns": list(df.columns),
                "post_rtcb_rows": int(is_post),
                "null_pct": round(df.isnull().mean().mean() * 100, 2),
            })
        except Exception as e:
            month_summaries.append({"month": f.stem, "error": str(e)})

    return {
        "exists": True,
        "file_count": len(files),
        "size_mb": round(total_bytes / 1_048_576, 1),
        "months": month_summaries,
    }


def build_manifest() -> dict:
    manifest = {
        "version": "v0.1",
        "hybridbid_dir": str(HYBRIDBID_DIR),
        "raw": {},
        "processed": {},
    }

    logger.info("Auditing raw products...")
    for product in RAW_PRODUCTS:
        logger.info("  %s", product)
        manifest["raw"][product] = audit_raw_product(product)

    logger.info("Auditing processed tables...")
    for table in PROCESSED_TABLES:
        logger.info("  %s", table)
        manifest["processed"][table] = audit_processed_table(table)

    return manifest


def write_markdown(manifest: dict, path: Path) -> None:
    lines = [
        "# v0.1 Data Manifest",
        "",
        f"Source: `{manifest['hybridbid_dir']}`",
        "",
        "## Raw products",
        "",
        "| Product | Files | Date range | Size (MB) | Missing days |",
        "|---------|-------|------------|-----------|--------------|",
    ]
    for product, info in manifest["raw"].items():
        if not info.get("exists"):
            lines.append(f"| {product} | ❌ NOT FOUND | — | — | — |")
            continue
        lines.append(
            f"| {product} | {info.get('file_count', 0)} | "
            f"{info.get('date_first', '?')} – {info.get('date_last', '?')} | "
            f"{info.get('size_mb', 0)} | {info.get('missing_count', 0)} |"
        )
    lines += ["", "## Processed tables", ""]
    for table, info in manifest["processed"].items():
        if not info.get("exists"):
            lines += [f"### {table}: ❌ NOT FOUND", ""]
            continue
        lines += [
            f"### {table}",
            f"Files: {info['file_count']}, Total size: {info['size_mb']} MB",
            "",
            "| Month | Rows | Post-RTC+B rows | Null % |",
            "|-------|------|-----------------|--------|",
        ]
        for m in info.get("months", []):
            if "error" in m:
                lines.append(f"| {m['month']} | ERROR: {m['error']} | — | — |")
            else:
                lines.append(
                    f"| {m['month']} | {m['rows']:,} | "
                    f"{m.get('post_rtcb_rows', '?'):,} | {m.get('null_pct', '?')}% |"
                )
        lines.append("")
    path.write_text("\n".join(lines) + "\n")
    logger.info("Wrote %s", path)


def main() -> None:
    manifest = build_manifest()

    json_path = AUDIT_DIR / "v0_1_manifest.json"
    json_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Wrote %s", json_path)

    write_markdown(manifest, AUDIT_DIR / "v0_1_manifest.md")
    logger.info("Audit complete.")


if __name__ == "__main__":
    main()
