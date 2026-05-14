"""ASDC ingest pipeline (ADR 0003).

Two sources:
  1. np4-212-cd (Report Type ID 24893) — ERCOT MISAPP public daily zip/CSV.
     Writes ASDCHourly Parquet under data/processed/v0.1/asdc_hourly/.
  2. AORDC Regression Fit Parameters xlsx — static mixture-normal constants.
     Writes ASDCParameters Parquet to data/processed/v0.1/asdc_params.parquet.

Both sources are public; no authentication required.
"""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from ercot_rtcb_bench.data.schema import ASDCHourly, ASDCParameters, ASProduct

logger = logging.getLogger(__name__)

# ── ERCOT MISAPP constants ────────────────────────────────────────────────────

MISAPP_BASE = "https://www.ercot.com"
MISAPP_LIST_URL = (
    f"{MISAPP_BASE}/misapp/GetReports.do"
    "?reportTypeId=24893"
    "&reportTitle=DAM+and+SCED+Ancillary+Service+Demand+Curves"
    "&showHTMLView=&mimicKey"
)
MISAPP_DL_URL = f"{MISAPP_BASE}/misdownload/servlets/mirDownload"

# ERCOT product name → canonical ASProduct value
_PRODUCT_MAP: dict[str, str] = {
    "regup": "regup",
    "reg-up": "regup",
    "reg up": "regup",
    "regulation up": "regup",
    "regdn": "regdn",
    "reg-dn": "regdn",
    "reg dn": "regdn",
    "reg down": "regdn",
    "regulation down": "regdn",
    "rrs": "rrs",
    "responsive reserve": "rrs",
    "responsive reserve service": "rrs",
    "ecrs": "ecrs",
    "ercot contingency reserve service": "ecrs",
    "nspin": "nspin",
    "non-spin": "nspin",
    "non spin": "nspin",
    "non-spinning": "nspin",
    "non spinning reserve": "nspin",
}

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "ercot-rtcb-bench/0.1 (research)"})


# ── MISAPP listing and download ───────────────────────────────────────────────


def _list_misapp_docs(report_date: str) -> list[dict]:
    """Scrape MISAPP listing for np4-212-cd and return doc entries for report_date.

    Returns list of dicts with keys: doclookup_id, filename.
    report_date format: 'YYYYMMDD'.
    """
    resp = _SESSION.get(MISAPP_LIST_URL, timeout=30)
    resp.raise_for_status()
    # Find links matching: doclookupId=XXXXXX with filename containing the date
    pattern = re.compile(
        r'doclookupId=(\d+)[^"]*"[^>]*>([^<]*NP4-212-CD[^<]*' + report_date + r'[^<]*)<',
        re.IGNORECASE,
    )
    matches = pattern.findall(resp.text)
    return [{"doclookup_id": m[0], "filename": m[1].strip()} for m in matches]


def _download_zip(doclookup_id: str) -> bytes:
    """Download a zip file from ERCOT MISAPP by doclookup_id."""
    resp = _SESSION.get(
        MISAPP_DL_URL,
        params={"doclookupId": doclookup_id},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def _fetch_with_retry(fn, *args, max_retries: int = 4, base_delay: float = 3.0, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                delay = base_delay * (2**attempt)
                logger.warning("Rate-limited; retry in %.1fs", delay)
                time.sleep(delay)
            elif attempt < max_retries - 1:
                time.sleep(base_delay)
            else:
                raise
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(base_delay)
            else:
                raise


# ── np4-212-cd parsing ───────────────────────────────────────────────────────


def _norm_col(s: str) -> str:
    """Canonical column name: lowercase, non-alphanumeric chars → _, collapse, strip."""
    s = re.sub(r"[^\w]+", "_", s.strip().lower())
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names using _norm_col."""
    df.columns = [_norm_col(c) for c in df.columns]
    return df


def _map_product(raw: str) -> str:
    key = raw.strip().lower()
    mapped = _PRODUCT_MAP.get(key)
    if mapped is None:
        raise ValueError(f"Unknown AS product name in np4-212-cd: {raw!r}")
    return mapped


def _parse_np4_212_csv(csv_bytes: bytes, source_filename: str) -> list[dict]:
    """Parse a single np4-212-cd CSV file into a list of row dicts.

    Expected columns (after normalization):
      operating_date, hour_ending, as_type (or as_product/product),
      segment (or segment_index/segment_no), breakpoint_mw,
      price_$_mw_h (or breakpoint_price/price), as_plan_mw
    """
    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    df = _normalize_columns(df)

    # --- Resolve column name variants ---
    col_map: dict[str, str] = {}

    for c in ("operating_date", "operatingdate", "oper_date", "date"):
        if c in df.columns:
            col_map["operating_date"] = c
            break

    for c in ("hour_ending", "hourending", "hour"):
        if c in df.columns:
            col_map["hour_ending"] = c
            break

    for c in ("as_type", "as_product", "product", "ancillary_type", "ancillary_service"):
        if c in df.columns:
            col_map["as_product"] = c
            break

    for c in ("segment", "segment_no", "segment_no.", "segment_index", "seg_no", "seg"):
        if c in df.columns:
            col_map["segment_index"] = c
            break

    for c in ("breakpoint_mw", "breakpoint_quantity_mw", "quantity_mw", "quantity"):
        if c in df.columns:
            col_map["breakpoint_mw"] = c
            break

    # Search for price column by matching normalized names
    _normed = {_norm_col(c): c for c in df.columns}
    for v in (
        "price_mw_h",      # "Price ($/MW-h)" → after _norm_col
        "breakpoint_price",
        "clearing_price",
        "price",
        "price___mw_h",    # legacy variants kept for safety
        "price__mw_h",
    ):
        if _norm_col(v) in _normed:
            col_map["breakpoint_price"] = _normed[_norm_col(v)]
            break

    for c in ("as_plan_mw", "as_plan", "ancillary_service_plan_mw"):
        if c in df.columns:
            col_map["as_plan_mw"] = c
            break

    missing = [
        k for k in ("operating_date", "hour_ending", "as_product",
                    "segment_index", "breakpoint_mw", "breakpoint_price")
        if k not in col_map
    ]
    if missing:
        raise ValueError(
            f"Cannot parse {source_filename}: missing columns for {missing}. "
            f"Available: {list(df.columns)}"
        )

    rows = []
    for _, row in df.iterrows():
        try:
            operating_date = pd.to_datetime(row[col_map["operating_date"]]).date()
            hour_ending = int(float(row[col_map["hour_ending"]]))
            as_product_str = _map_product(row[col_map["as_product"]])
            segment_index = int(float(row[col_map["segment_index"]]))
            breakpoint_mw = float(row[col_map["breakpoint_mw"]])
            breakpoint_price = float(row[col_map["breakpoint_price"]])
            as_plan_mw = float(row[col_map["as_plan_mw"]]) if "as_plan_mw" in col_map else 0.0

            rows.append({
                "operating_date": operating_date,
                "hour_ending": hour_ending,
                "as_product": as_product_str,
                "segment_index": segment_index,
                "breakpoint_mw": breakpoint_mw,
                "breakpoint_price": breakpoint_price,
                "as_plan_mw": as_plan_mw,
                "source_filename": source_filename,
            })
        except (ValueError, KeyError) as e:
            logger.debug("Skipping malformed row: %s — %s", dict(row), e)
            continue

    return rows


def _parse_np4_212_zip(zip_bytes: bytes, zip_filename: str) -> pd.DataFrame:
    """Unzip and parse all CSV files in an np4-212-cd zip."""
    all_rows: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            csv_bytes = zf.read(name)
            rows = _parse_np4_212_csv(csv_bytes, source_filename=name)
            all_rows.extend(rows)

    if not all_rows:
        raise ValueError(f"No rows parsed from {zip_filename}")

    df = pd.DataFrame(all_rows)
    _spot_validate_asdc_hourly(df)
    return df


def _spot_validate_asdc_hourly(df: pd.DataFrame) -> None:
    """Spot-validate a sample of rows against ASDCHourly schema."""
    sample = df.sample(min(20, len(df)), random_state=42)
    for _, row in sample.iterrows():
        ASDCHourly(**row.to_dict())


# ── Public ingest API ─────────────────────────────────────────────────────────


def ingest_asdc_hourly_date(
    report_date: date,
    out_dir: Path,
    cache_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """Fetch and persist ASDCHourly for one operating date.

    Args:
        report_date: The operating date to ingest.
        out_dir: Directory to write per-date Parquet files.
        cache_dir: Optional raw zip cache directory (skips MISAPP if hit).
        force: Re-download even if output Parquet exists.

    Returns:
        Path to the written Parquet file.
    """
    date_str = report_date.strftime("%Y%m%d")
    out_path = out_dir / f"{report_date.isoformat()}.parquet"
    if out_path.exists() and not force:
        logger.debug("Already ingested: %s", out_path)
        return out_path

    out_dir.mkdir(parents=True, exist_ok=True)

    zip_filename = f"NP4-212-CD_{date_str}.zip"
    zip_path = (cache_dir / zip_filename) if cache_dir else None

    if zip_path and zip_path.exists():
        zip_bytes = zip_path.read_bytes()
        logger.info("Loaded from cache: %s", zip_path)
    else:
        docs = _fetch_with_retry(_list_misapp_docs, date_str)
        if not docs:
            raise FileNotFoundError(
                f"No np4-212-cd file found for {report_date} on MISAPP"
            )
        doc = docs[0]
        logger.info(
            "Downloading doclookupId=%s (%s)", doc["doclookup_id"], doc["filename"]
        )
        zip_bytes = _fetch_with_retry(_download_zip, doc["doclookup_id"])

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            zip_path.write_bytes(zip_bytes)
            logger.debug("Cached zip to %s", zip_path)

    df = _parse_np4_212_zip(zip_bytes, zip_filename)
    df.to_parquet(out_path, compression="snappy", index=False)
    logger.info("Wrote %d rows → %s", len(df), out_path)
    return out_path


def ingest_asdc_hourly_range(
    start: date,
    end: date,
    out_dir: Path,
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict[date, bool]:
    """Ingest ASDCHourly for all dates in [start, end).

    Returns dict mapping operating_date → success.
    """
    results: dict[date, bool] = {}
    for d in pd.date_range(start=start, end=end, freq="D", inclusive="left"):
        d_date = d.date()
        try:
            ingest_asdc_hourly_date(d_date, out_dir, cache_dir, force)
            results[d_date] = True
        except Exception as e:
            logger.error("Failed %s: %s", d_date, e)
            results[d_date] = False
        time.sleep(1.0)  # rate-limit ERCOT MISAPP requests
    return results


def load_asdc_hourly(data_dir: Path) -> pd.DataFrame:
    """Load all ASDCHourly Parquet files from data_dir into one DataFrame."""
    frames = [pd.read_parquet(f) for f in sorted(data_dir.glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ── AORDC xlsx parser ─────────────────────────────────────────────────────────

_AORDC_COL_VARIANTS: dict[str, list[str]] = {
    "as_product": ["as product", "product", "ancillary service", "as_product"],
    "mu": ["mu", "μ", "mean", "mu (mw)"],
    "sigma": ["sigma", "σ", "std dev", "standard deviation", "sigma (mw)"],
    "mix_weight_30min": [
        "mix weight 30min", "mix weight 30-min", "w_30", "weight_30", "30-min weight",
    ],
    "mix_weight_60min": [
        "mix weight 60min", "mix weight 60-min", "w_60", "weight_60", "60-min weight",
    ],
    "voll": ["voll", "value of lost load", "voll ($/mwh)"],
    "voll_cap_offset": [
        "voll cap offset", "voll_cap_offset", "cap offset", "cap_offset ($)", "offset",
    ],
    "min_step_floor": [
        "min step floor", "min_step_floor", "floor", "minimum step floor",
        "floor ($/mw-h)",
    ],
}


def _resolve_col(df: pd.DataFrame, canonical: str) -> str | None:
    """Find df column matching canonical field, comparing after _norm_col on both sides."""
    variants = _AORDC_COL_VARIANTS.get(canonical, [canonical])
    normed_cols = {_norm_col(c): c for c in df.columns}
    for v in variants:
        nv = _norm_col(v)
        if nv in normed_cols:
            return normed_cols[nv]
    return None


def parse_aordc_xlsx(
    xlsx_path: Path,
    effective_date: date,
    source_url: str = "https://www.ercot.com/calendar/2025/9/30/249105",
    source_doc_revision: str = "RTC+B go-live 2025-09-30",
) -> list[ASDCParameters]:
    """Parse ERCOT AORDC Regression Fit Parameters xlsx into ASDCParameters records.

    Args:
        xlsx_path: Path to the downloaded xlsx file.
        effective_date: The effective date for this parameter set.
        source_url: URL where the xlsx was obtained.
        source_doc_revision: Human-readable revision string.

    Returns:
        List of ASDCParameters (one per AS product row found).
    """
    xl = pd.ExcelFile(xlsx_path)
    df: pd.DataFrame | None = None
    for sheet in xl.sheet_names:
        candidate = xl.parse(sheet, dtype=str)
        candidate = _normalize_columns(candidate)
        if _resolve_col(candidate, "as_product") and _resolve_col(candidate, "mu"):
            df = candidate
            logger.info("Parsed AORDC params from sheet %r", sheet)
            break

    if df is None:
        raise ValueError(
            f"No recognizable ASDC parameter sheet found in {xlsx_path}"
        )

    records: list[ASDCParameters] = []
    for _, row in df.iterrows():
        raw_product = row.get(_resolve_col(df, "as_product") or "", "")
        if not isinstance(raw_product, str) or not raw_product.strip():
            continue
        try:
            as_product_str = _map_product(raw_product.strip())
        except ValueError:
            logger.debug("Skipping unrecognized product %r", raw_product)
            continue

        def _f(field: str) -> float:
            col = _resolve_col(df, field)  # type: ignore[arg-type]
            if col is None:
                raise ValueError(f"Missing column for {field!r} in xlsx")
            return float(row[col])

        try:
            params = ASDCParameters(
                as_product=ASProduct(as_product_str),
                effective_date=effective_date,
                mu=_f("mu"),
                sigma=_f("sigma"),
                mix_weight_30min=_f("mix_weight_30min"),
                mix_weight_60min=_f("mix_weight_60min"),
                voll=_f("voll"),
                voll_cap_offset=_f("voll_cap_offset"),
                min_step_floor=_f("min_step_floor"),
                source_url=source_url,
                source_doc_revision=source_doc_revision,
            )
            records.append(params)
        except Exception as e:
            logger.warning("Skipping row for product %r: %s", raw_product, e)

    if not records:
        raise ValueError(f"No ASDCParameters records parsed from {xlsx_path}")
    return records


def save_asdc_params(params: list[ASDCParameters], out_path: Path) -> None:
    """Serialize ASDCParameters list to Parquet."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([p.model_dump() for p in params])
    df.to_parquet(out_path, compression="snappy", index=False)
    logger.info("Wrote %d ASDCParameters rows → %s", len(df), out_path)


def load_asdc_params(parquet_path: Path) -> list[ASDCParameters]:
    """Load ASDCParameters from Parquet and validate against schema."""
    df = pd.read_parquet(parquet_path)
    return [ASDCParameters(**row) for row in df.to_dict(orient="records")]
