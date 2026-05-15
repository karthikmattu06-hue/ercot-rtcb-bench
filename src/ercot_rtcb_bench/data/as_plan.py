"""AS Plan ingest pipeline (ADR 0005).

Two sources following the two-surface pattern established for np4-212-cd:
  1. np4-33-CD (Report Type ID 12316) — ERCOT MISAPP public daily CSV/zip.
     Fetched via fetch_as_plan_current() for recent ~31-day rolling window.
  2. ERCOT Public Data API archive — historical backfill beyond 31 days.
     Fetched via backfill_as_plan_history().

np4-33-CD Report Type ID = 12316
Empirically determined on 2026-05-14 via ERCOT product detail page.
Reference: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-33-CD

CSV schema observed on first fetch (2026-05-14):
  DeliveryDate, HourEnding, AncillaryType, Quantity, DSTFlag
  - DeliveryDate: MM/DD/YYYY
  - HourEnding:   HH:MM  (ERCOT convention; "01:00" = hour_ending 1)
  - AncillaryType: ECRS | NSPIN | REGUP | REGDN | RRS
  - Quantity: MW (integer in practice; stored as float)
  - DSTFlag: Y | N (ignored; we deduplicate by operating_date + hour_ending)

Each MISAPP/archive file covers 7 operating days from the publication date.
Multiple publications for overlapping windows are deduplicated by
(operating_date, hour_ending), keeping the most recent revision.

The raw long-format CSV is pivoted to wide format to match the ASPlan schema
(one row per operating hour, five product columns).
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

from ercot_rtcb_bench.data.schema import ASPlan

logger = logging.getLogger(__name__)

# ── np4-33-CD constants ───────────────────────────────────────────────────────

NP4_33_CD_REPORT_TYPE_ID = 12316

MISAPP_BASE = "https://www.ercot.com"
MISAPP_LIST_URL = (
    f"{MISAPP_BASE}/misapp/GetReports.do"
    f"?reportTypeId={NP4_33_CD_REPORT_TYPE_ID}"
    "&reportTitle=DAM+Ancillary+Service+Plan"
    "&showHTMLView=&mimicKey"
)
MISAPP_DL_URL = f"{MISAPP_BASE}/misdownload/servlets/mirDownload"

# ── ERCOT Public Data API constants ──────────────────────────────────────────

ERCOT_API_BASE = "https://api.ercot.com"
# Azure B2C ROPC token endpoint (same for all ERCOT Public API products)
ERCOT_TOKEN_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
    "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
# ERCOT's published public-API client_id (not a secret)
ERCOT_CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"

BATCH_SIZE = 50        # kept for compatibility; not used in JSON API path
BATCH_SLEEP = 2.0      # seconds between API pages (30 req/min → 2s floor)

# ── AncillaryType → ASPlan wide column ───────────────────────────────────────

_PRODUCT_COL: dict[str, str] = {
    "regup": "rureq",
    "reg-up": "rureq",
    "reg up": "rureq",
    "regulation up": "rureq",
    "regdn": "regdnreq",
    "reg-dn": "regdnreq",
    "reg dn": "regdnreq",
    "reg down": "regdnreq",
    "regulation down": "regdnreq",
    "rrs": "rrsreq",
    "responsive reserve": "rrsreq",
    "responsive reserve service": "rrsreq",
    "ecrs": "ecrsreq",
    "ercot contingency reserve service": "ecrsreq",
    "nspin": "nspinreq",
    "non-spin": "nspinreq",
    "non spin": "nspinreq",
    "non-spinning": "nspinreq",
    "non spinning reserve": "nspinreq",
}

_AS_PLAN_COLS = ["rureq", "regdnreq", "rrsreq", "ecrsreq", "nspinreq"]

# ── Shared MISAPP session ─────────────────────────────────────────────────────

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "ercot-rtcb-bench/0.1 (research)"})


# ── Column normalizer (matches asdc.py pattern) ───────────────────────────────


def _norm_col(s: str) -> str:
    """Canonical column name: lowercase, non-alphanumeric → _, collapse, strip."""
    s = re.sub(r"[^\w]+", "_", s.strip().lower())
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _parse_hour_ending(raw: str) -> int:
    """Convert ERCOT HourEnding string to integer 1..24.

    Handles both HH:MM ("01:00" → 1, "24:00" → 24) and plain integers.
    """
    raw = str(raw).strip()
    if ":" in raw:
        return int(raw.split(":")[0])
    return int(float(raw))


# ── CSV parser ────────────────────────────────────────────────────────────────


def parse_as_plan_csv(zip_or_csv_bytes: bytes, source_filename: str) -> pd.DataFrame:
    """Parse np4-33-CD CSV (or zip containing CSV) → wide-format DataFrame.

    Input CSV columns (long format, one row per product per hour):
        DeliveryDate, HourEnding, AncillaryType, Quantity, DSTFlag

    Output DataFrame columns (wide format, one row per operating hour):
        operating_date, hour_ending, rureq, regdnreq, rrsreq, ecrsreq, nspinreq

    Each publication file covers 7 operating days from the publication date.
    Deduplication across publications is done in the caller.

    Args:
        zip_or_csv_bytes: Raw bytes of either a zip (containing a CSV) or a CSV.
        source_filename:  Name of the source file for logging.

    Returns:
        DataFrame with one row per (operating_date, hour_ending) per publication.

    Raises:
        ValueError: If no rows can be parsed or required columns are missing.
    """
    csv_frames: list[pd.DataFrame] = []

    if _is_zip(zip_or_csv_bytes):
        with zipfile.ZipFile(io.BytesIO(zip_or_csv_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    csv_frames.append(_parse_single_csv(zf.read(name), source_filename=name))
    else:
        csv_frames.append(_parse_single_csv(zip_or_csv_bytes, source_filename))

    if not csv_frames:
        raise ValueError(f"No CSV data found in {source_filename}")

    raw_long = pd.concat(csv_frames, ignore_index=True)

    # Pivot long → wide
    df = (
        raw_long
        .pivot_table(
            index=["operating_date", "hour_ending"],
            columns="col_name",
            values="quantity_mw",
            aggfunc="last",
        )
        .reset_index()
    )
    df.columns.name = None

    # Ensure all 5 product columns are present (fill missing with 0)
    for col in _AS_PLAN_COLS:
        if col not in df.columns:
            logger.warning("%s: missing product column %r — filling with 0", source_filename, col)
            df[col] = 0.0

    df = df[["operating_date", "hour_ending"] + _AS_PLAN_COLS]
    df = df.sort_values(["operating_date", "hour_ending"]).reset_index(drop=True)

    _spot_validate_as_plan(df, source_filename)
    return df


def _is_zip(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _parse_single_csv(csv_bytes: bytes, source_filename: str) -> pd.DataFrame:
    """Parse one AS Plan CSV file into long-format DataFrame."""
    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    df.columns = [_norm_col(c) for c in df.columns]

    normed = {_norm_col(c): c for c in df.columns}

    def _find(candidates: list[str]) -> str | None:
        for c in candidates:
            if _norm_col(c) in normed:
                return normed[_norm_col(c)]
        return None

    date_col = _find(["deliverydate", "delivery_date", "operating_date", "date"])
    hour_col = _find(["hourending", "hour_ending", "hour"])
    type_col = _find(["ancillarytype", "ancillary_type", "as_type", "as_product", "product"])
    qty_col = _find(["quantity", "quantity_mw", "mw", "requirement_mw"])

    missing = [
        name
        for name, col in [
            ("DeliveryDate", date_col), ("HourEnding", hour_col),
            ("AncillaryType", type_col), ("Quantity", qty_col),
        ]
        if col is None
    ]
    if missing:
        raise ValueError(
            f"Cannot parse {source_filename}: missing columns for {missing}. "
            f"Available (normalized): {list(df.columns)}"
        )

    rows: list[dict] = []
    for _, row in df.iterrows():
        try:
            raw_type = str(row[type_col]).strip().lower()  # type: ignore[index]
            col_name = _PRODUCT_COL.get(raw_type)
            if col_name is None:
                logger.debug("Unknown AncillaryType %r — skipping", raw_type)
                continue

            operating_date = pd.to_datetime(row[date_col]).date()  # type: ignore[index]
            hour_ending = _parse_hour_ending(row[hour_col])  # type: ignore[index]
            quantity_mw = float(row[qty_col])  # type: ignore[index]

            rows.append({
                "operating_date": operating_date,
                "hour_ending": hour_ending,
                "col_name": col_name,
                "quantity_mw": quantity_mw,
            })
        except (ValueError, KeyError) as e:
            logger.debug("Skipping row in %s: %s — %s", source_filename, dict(row), e)

    if not rows:
        raise ValueError(f"No rows parsed from {source_filename}")
    return pd.DataFrame(rows)


def _spot_validate_as_plan(df: pd.DataFrame, source_filename: str) -> None:
    """Spot-validate a sample of rows against ASPlan schema."""
    sample = df.sample(min(20, len(df)), random_state=42)
    for _, row in sample.iterrows():
        try:
            ASPlan(**row.to_dict())
        except Exception as e:
            logger.warning("Schema validation failed in %s: %s", source_filename, e)


# ── Retry helper ──────────────────────────────────────────────────────────────


def _fetch_with_retry(
    fn,
    *args,
    max_retries: int = 4,
    base_delay: float = 3.0,
    **kwargs,
):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Rate-limited; retry %d/%d in %.1fs", attempt + 1, max_retries, delay
                )
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


# ── MISAPP helpers ────────────────────────────────────────────────────────────


def _list_all_misapp_docs() -> list[dict]:
    """Fetch the full MISAPP listing for np4-33-CD and return all CSV entries.

    Each entry: {"doclookup_id": str, "filename": str}.
    The listing contains ~31 days of rolling publications; each covers 7 days.

    HTML structure: doclookupIds and filenames are in parallel order inside
    separate tags. We extract them separately then zip them together, keeping
    only the CSV entries (filename contains "csv").
    """
    resp = _SESSION.get(MISAPP_LIST_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text

    # Extract all doclookupIds in document order
    all_ids = re.findall(r"doclookupId=(\d+)", text)
    # Extract all filenames from labelOptional_ind cells
    all_filenames = re.findall(r"labelOptional_ind'>([^<]+)</td>", text)

    if not all_ids or not all_filenames:
        logger.warning("MISAPP listing parse found 0 IDs or 0 filenames; HTML may have changed")
        return []

    if len(all_ids) != len(all_filenames):
        logger.warning(
            "MISAPP ID count (%d) ≠ filename count (%d); pairing by min length",
            len(all_ids), len(all_filenames),
        )

    docs = []
    for doc_id, filename in zip(all_ids, all_filenames):
        filename = filename.strip()
        if "csv" in filename.lower():
            docs.append({"doclookup_id": doc_id, "filename": filename})

    logger.debug("MISAPP: found %d CSV publications", len(docs))
    return docs


def _download_misapp_zip(doclookup_id: str) -> bytes:
    resp = _SESSION.get(
        MISAPP_DL_URL, params={"doclookupId": doclookup_id}, timeout=60
    )
    resp.raise_for_status()
    return resp.content


# ── MISAPP current-data fetch ─────────────────────────────────────────────────


def fetch_as_plan_current(
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Fetch AS Plan from MISAPP and return a DataFrame filtered to [date_from, date_to].

    Downloads all available publications from MISAPP (~31-day rolling window,
    each publication covering 7 operating days). After parsing, deduplicates
    by (operating_date, hour_ending) and filters to the requested range.

    MISAPP retains ~31 days of rolling publications. For older data use
    backfill_as_plan_history().

    Args:
        date_from: First operating date to include (inclusive).
        date_to:   Last operating date to include (inclusive).

    Returns:
        DataFrame with columns: operating_date, hour_ending, rureq, regdnreq,
        rrsreq, ecrsreq, nspinreq.  One row per (operating_date, hour_ending).
    """
    docs = _fetch_with_retry(_list_all_misapp_docs)
    if not docs:
        logger.warning("No np4-33-CD publications found on MISAPP")
        return pd.DataFrame()

    logger.info("Found %d MISAPP publications; downloading...", len(docs))
    all_frames: list[pd.DataFrame] = []

    for doc in docs:
        try:
            zip_bytes = _fetch_with_retry(_download_misapp_zip, doc["doclookup_id"])
            df = parse_as_plan_csv(zip_bytes, doc["filename"])
            all_frames.append(df)
        except Exception as e:
            logger.warning("Failed %s: %s", doc["filename"], e)
        time.sleep(1.0)

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)
    # Deduplicate: keep last revision for each (operating_date, hour_ending)
    combined = (
        combined
        .drop_duplicates(subset=["operating_date", "hour_ending"], keep="last")
        .sort_values(["operating_date", "hour_ending"])
        .reset_index(drop=True)
    )
    # Filter to requested range
    mask = (combined["operating_date"] >= date_from) & (combined["operating_date"] <= date_to)
    result = combined[mask].reset_index(drop=True)
    logger.info(
        "fetch_as_plan_current: %d rows for %s..%s", len(result), date_from, date_to
    )
    return result


# ── ERCOT Public Data API auth ────────────────────────────────────────────────

# Authenticated JSON endpoint (empirically confirmed 2026-05-14):
#   GET /api/public-reports/np4-33-cd/dam_as_plan
#   Params: deliveryDateFrom (YYYY-MM-DD), deliveryDateTo (YYYY-MM-DD),
#           size (rows per page), page (1-based)
#   Response: {"_meta": {..., "totalPages": N}, "fields": [...], "data": [[...],...]}
#   Sort:  postedDatetime DESC → first row per group = most recent revision
ERCOT_DATA_URL = f"{ERCOT_API_BASE}/api/public-reports/np4-33-cd/dam_as_plan"
API_PAGE_SIZE = 1000   # max rows per request (downloadLimit = 2,000,000)


def _get_api_token(username: str, password: str) -> str:
    """Obtain a Bearer token via the ERCOT Azure B2C ROPC flow."""
    resp = requests.post(
        ERCOT_TOKEN_URL,
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
            "response_type": "id_token",
            "scope": f"openid {ERCOT_CLIENT_ID} offline_access",
            "client_id": ERCOT_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("id_token") or payload["access_token"]


def _api_headers(token: str, sub_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": sub_key,
    }


def _fetch_api_page(
    token: str,
    sub_key: str,
    date_from: date,
    date_to: date,
    page: int = 1,
    size: int = API_PAGE_SIZE,
) -> tuple[list[list], list[str], int]:
    """Fetch one page of dam_as_plan JSON records.

    Returns (data_rows, field_names, total_pages).
    data_rows is a list of lists (values match field_names order).
    """
    resp = requests.get(
        ERCOT_DATA_URL,
        headers=_api_headers(token, sub_key),
        params={
            "deliveryDateFrom": date_from.isoformat(),
            "deliveryDateTo": date_to.isoformat(),
            "size": size,
            "page": page,
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    meta = payload.get("_meta", {})
    fields = [f["name"] for f in payload.get("fields", [])]
    data = payload.get("data", [])
    total_pages = int(meta.get("totalPages", 1))
    return data, fields, total_pages


def _api_rows_to_df(data: list[list], fields: list[str]) -> pd.DataFrame:
    """Convert raw API rows (list of lists) to a long-format DataFrame."""
    if not data or not fields:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=fields)
    # Rename to match our internal conventions
    rename = {
        "deliveryDate": "delivery_date",
        "hourEnding": "hour_ending_str",
        "ancillaryType": "ancillary_type",
        "quantity": "quantity_mw",
        "DSTFlag": "dst_flag",
        "postedDatetime": "posted_datetime",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df


# ── Historical backfill (JSON API) ────────────────────────────────────────────


def backfill_as_plan_history(
    date_from: date,
    date_to: date,
    out_dir: Path,
    username: str,
    password: str,
    sub_key: str,
    force: bool = False,
) -> dict[str, int]:
    """Backfill AS Plan from the ERCOT Public Data API JSON endpoint.

    Calls GET /api/public-reports/np4-33-cd/dam_as_plan with
    deliveryDateFrom / deliveryDateTo params. The API returns all postings
    sorted postedDatetime DESC, so the first occurrence of each
    (deliveryDate, hourEnding, ancillaryType) tuple is the latest revision.
    After dedup, pivots long → wide and writes monthly Parquet files.

    Rate limits: API_PAGE_SIZE = 1000 rows/request; BATCH_SLEEP between pages.

    Args:
        date_from:  First operating date to backfill.
        date_to:    Last operating date to backfill (inclusive).
        out_dir:    Directory for monthly Parquet files (YYYY-MM.parquet).
        username:   ERCOT_API_USERNAME.
        password:   ERCOT_API_PASSWORD.
        sub_key:    ERCOT_PUBLIC_API_SUBSCRIPTION_KEY.
        force:      Overwrite existing monthly Parquets.

    Returns:
        Dict mapping month_str (e.g., "2026-01") → row_count.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Skip if all months already present
    if not force:
        existing_months = {f.stem for f in out_dir.glob("????-??.parquet")}
        needed_months = {
            d.strftime("%Y-%m")
            for d in pd.date_range(start=date_from, end=date_to, freq="MS")
        }
        if needed_months and needed_months <= existing_months:
            logger.info("All months already present; skipping backfill.")
            return {m: 0 for m in existing_months}

    logger.info("Authenticating with ERCOT Public Data API...")
    token = _fetch_with_retry(_get_api_token, username, password)
    logger.info("Token obtained.")

    # Fetch month by month to keep per-request row counts manageable
    # (Dec 2025 has ~27 days × 7 postings × 5 products × 24 hours ≈ 22,680 rows)
    monthly_counts: dict[str, int] = {}

    # Start from the 1st of the month containing date_from so partial months
    # (e.g., Dec 5 start) are included; freq="MS" alone would skip to Jan.
    first_month = date_from.replace(day=1)
    for month_start in pd.date_range(start=first_month, end=date_to, freq="MS"):
        month_str = month_start.strftime("%Y-%m")
        out_path = out_dir / f"{month_str}.parquet"
        if out_path.exists() and not force:
            logger.info("  %s: already present, skipping.", month_str)
            monthly_counts[month_str] = len(pd.read_parquet(out_path))
            continue

        # Month window clipped to [date_from, date_to]
        m_from = max(date_from, month_start.date())
        m_to = min(date_to, (month_start + pd.offsets.MonthEnd(1)).date())

        logger.info("  Fetching %s: %s … %s", month_str, m_from, m_to)
        all_rows: list[list] = []
        fields: list[str] = []
        page = 1
        while True:
            try:
                data, fields, total_pages = _fetch_with_retry(
                    _fetch_api_page, token, sub_key, m_from, m_to, page, API_PAGE_SIZE
                )
            except Exception as e:
                logger.error("    Page %d failed: %s", page, e)
                break
            all_rows.extend(data)
            logger.info("    Page %d/%d: +%d rows", page, total_pages, len(data))
            if page >= total_pages or not data:
                break
            page += 1
            time.sleep(BATCH_SLEEP)

        if not all_rows or not fields:
            logger.warning("  %s: no data returned", month_str)
            continue

        raw_long = _api_rows_to_df(all_rows, fields)

        # Deduplicate: API is sorted postedDatetime DESC → keep first per group
        raw_long = raw_long.drop_duplicates(
            subset=["delivery_date", "hour_ending_str", "ancillary_type"],
            keep="first",
        )

        # Map ancillaryType → wide column name
        raw_long["col_name"] = raw_long["ancillary_type"].str.strip().str.lower().map(_PRODUCT_COL)
        unknown = raw_long["col_name"].isna()
        if unknown.any():
            logger.warning(
                "  %s: %d rows with unknown ancillaryType: %s",
                month_str, unknown.sum(),
                raw_long.loc[unknown, "ancillary_type"].unique().tolist(),
            )
        raw_long = raw_long[~unknown]

        # Parse operating_date and hour_ending
        raw_long["operating_date"] = pd.to_datetime(raw_long["delivery_date"]).dt.date
        raw_long["hour_ending"] = raw_long["hour_ending_str"].apply(_parse_hour_ending)
        raw_long["quantity_mw"] = raw_long["quantity_mw"].astype(float)

        # Pivot long → wide
        wide = (
            raw_long
            .pivot_table(
                index=["operating_date", "hour_ending"],
                columns="col_name",
                values="quantity_mw",
                aggfunc="first",
            )
            .reset_index()
        )
        wide.columns.name = None

        for col in _AS_PLAN_COLS:
            if col not in wide.columns:
                logger.warning("  %s: missing product column %r", month_str, col)
                wide[col] = 0.0

        wide = wide[["operating_date", "hour_ending"] + _AS_PLAN_COLS]
        wide = wide.sort_values(["operating_date", "hour_ending"]).reset_index(drop=True)

        _spot_validate_as_plan(wide, source_filename=month_str)
        wide.to_parquet(out_path, compression="snappy", index=False)
        monthly_counts[month_str] = len(wide)
        logger.info("  Wrote %d rows → %s", len(wide), out_path)

    return monthly_counts


# ── Load helper ───────────────────────────────────────────────────────────────


def load_as_plan(data_dir: Path) -> pd.DataFrame:
    """Load all AS Plan Parquet files from data_dir into one DataFrame."""
    frames = [pd.read_parquet(f) for f in sorted(data_dir.glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
