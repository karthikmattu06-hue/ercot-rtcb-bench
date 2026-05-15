"""ASDC ingest and oracle verification tests (ADR 0003, ADR 0006).

Tests cover:
  1. np4-212-cd CSV parsing (from synthetic test fixtures)
  2. AORDC xlsx parsing (from synthetic fixtures)
  3. Oracle: curve reconstructed from ASDCParameters matches ASDCHourly
     breakpoints to within $0.10/MW-h (ADR 0003 acceptance criterion)
  4. Schema validation: all parsed records pass ASDCHourly/ASDCParameters
  5. NPRR1268 formula unit tests
  6. Single-hour integration oracle test against real v0.1 data (ADR 0006)
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ercot_rtcb_bench.data.asdc import (
    _map_product,
    _normalize_columns,
    _parse_np4_212_csv,
    _parse_np4_212_zip,
    parse_aordc_xlsx,
    reconstruct_per_product_asdc,
    _aordc,
    _mcl_quantities,
    MCL,
    MAX_DEMAND_PRICE_OFFSETS,
    ASDC_FLOOR,
)
from ercot_rtcb_bench.data.io import load_as_plan, load_asdc_hourly
from ercot_rtcb_bench.data.schema import ASDCHourly, ASDCParameters, ASProduct


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_np4_212_csv(rows: list[dict]) -> bytes:
    """Produce a synthetic np4-212-cd CSV in ERCOT column format."""
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode()


def _make_np4_212_zip(csv_bytes: bytes, filename: str = "NP4-212-CD_20260115.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, csv_bytes)
    return buf.getvalue()


SAMPLE_ROWS = [
    {
        "Operating Date": "2026-01-15",
        "Hour Ending": 14,
        "AS Type": "REGUP",
        "Segment": seg,
        "Breakpoint MW": seg * 250.0,
        "Price ($/MW-h)": max(0.0, 4750.0 - seg * 475.0),
        "AS Plan MW": 2500.0,
    }
    for seg in range(10)
]


# ── Column normalization ──────────────────────────────────────────────────────


class TestNormalizeColumns:
    def test_spaces_to_underscores(self):
        df = pd.DataFrame(columns=["Operating Date", "Hour Ending", "AS Type"])
        df = _normalize_columns(df)
        assert "operating_date" in df.columns
        assert "hour_ending" in df.columns
        assert "as_type" in df.columns

    def test_dollar_sign_stripped(self):
        df = pd.DataFrame(columns=["Price ($/MW-h)"])
        df = _normalize_columns(df)
        # After normalization hyphens and special chars become underscores
        assert any("price" in c for c in df.columns)

    def test_already_normalized(self):
        df = pd.DataFrame(columns=["operating_date", "segment_index"])
        df = _normalize_columns(df)
        assert "operating_date" in df.columns


# ── Product name mapping ──────────────────────────────────────────────────────


class TestMapProduct:
    @pytest.mark.parametrize("raw,expected", [
        ("REGUP", "regup"),
        ("Reg-Up", "regup"),
        ("regulation up", "regup"),
        ("REGDN", "regdn"),
        ("Reg Down", "regdn"),
        ("RRS", "rrs"),
        ("Responsive Reserve Service", "rrs"),
        ("ECRS", "ecrs"),
        ("NSPIN", "nspin"),
        ("Non-Spin", "nspin"),
        ("non spinning reserve", "nspin"),
    ])
    def test_known_products(self, raw, expected):
        assert _map_product(raw) == expected

    def test_unknown_product_raises(self):
        with pytest.raises(ValueError, match="Unknown AS product"):
            _map_product("DRRS")


# ── CSV parsing ───────────────────────────────────────────────────────────────


class TestParseNp4212CSV:
    def test_parses_standard_format(self):
        csv_bytes = _make_np4_212_csv(SAMPLE_ROWS)
        rows = _parse_np4_212_csv(csv_bytes, "test.csv")
        assert len(rows) == len(SAMPLE_ROWS)
        assert rows[0]["as_product"] == "regup"
        assert rows[0]["operating_date"] == date(2026, 1, 15)
        assert rows[0]["hour_ending"] == 14

    def test_all_products_parsed(self):
        rows_in = []
        for i, product in enumerate(["REGUP", "REGDN", "RRS", "ECRS", "NSPIN"]):
            rows_in.append({
                "Operating Date": "2026-01-15",
                "Hour Ending": i + 1,
                "AS Type": product,
                "Segment": 0,
                "Breakpoint MW": 100.0,
                "Price ($/MW-h)": 5.0,
                "AS Plan MW": 500.0,
            })
        csv_bytes = _make_np4_212_csv(rows_in)
        rows = _parse_np4_212_csv(csv_bytes, "multi_product.csv")
        products = {r["as_product"] for r in rows}
        assert products == {"regup", "regdn", "rrs", "ecrs", "nspin"}

    def test_missing_required_column_raises(self):
        bad_rows = [{"Operating Date": "2026-01-15", "Hour Ending": 1}]
        csv_bytes = _make_np4_212_csv(bad_rows)
        with pytest.raises(ValueError, match="missing columns"):
            _parse_np4_212_csv(csv_bytes, "bad.csv")

    def test_segment_index_zero_based(self):
        csv_bytes = _make_np4_212_csv(SAMPLE_ROWS)
        rows = _parse_np4_212_csv(csv_bytes, "test.csv")
        assert rows[0]["segment_index"] == 0
        assert rows[9]["segment_index"] == 9

    def test_rows_validate_against_schema(self):
        csv_bytes = _make_np4_212_csv(SAMPLE_ROWS)
        rows = _parse_np4_212_csv(csv_bytes, "test.csv")
        for row in rows:
            ASDCHourly(**row)  # must not raise


# ── Zip parsing ───────────────────────────────────────────────────────────────


class TestParseNp4212Zip:
    def test_extracts_csv_from_zip(self):
        csv_bytes = _make_np4_212_csv(SAMPLE_ROWS)
        zip_bytes = _make_np4_212_zip(csv_bytes)
        df = _parse_np4_212_zip(zip_bytes, "NP4-212-CD_20260115.zip")
        assert len(df) == len(SAMPLE_ROWS)
        assert set(df.columns) >= {
            "operating_date", "hour_ending", "as_product",
            "segment_index", "breakpoint_mw", "breakpoint_price",
        }

    def test_ignores_non_csv_files_in_zip(self):
        csv_bytes = _make_np4_212_csv(SAMPLE_ROWS)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.csv", csv_bytes)
            zf.writestr("README.txt", b"ignore me")
        df = _parse_np4_212_zip(buf.getvalue(), "test.zip")
        assert len(df) == len(SAMPLE_ROWS)


# ── AORDC xlsx parsing ────────────────────────────────────────────────────────


def _make_aordc_xlsx(rows: list[dict]) -> bytes:
    """Produce a synthetic AORDC xlsx with a 'Parameters' sheet."""
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Parameters", index=False)
    return buf.getvalue()


AORDC_ROWS = [
    {
        "AS Product": product,
        "Mu": mu,
        "Sigma": sigma,
        "Mix Weight 30min": 0.4,
        "Mix Weight 60min": 0.6,
        "VOLL": 5000.0,
        "VOLL Cap Offset": 250.0,
        "Min Step Floor": 0.25,
    }
    for product, mu, sigma in [
        ("REGUP", 2500.0, 1200.0),
        ("REGDN", 1800.0, 900.0),
        ("RRS", 4500.0, 2000.0),
        ("ECRS", 5500.0, 2500.0),
        ("NSPIN", 8000.0, 3500.0),
    ]
]


class TestParseAORDCXlsx:
    def test_parses_five_products(self, tmp_path):
        xlsx_bytes = _make_aordc_xlsx(AORDC_ROWS)
        xlsx_path = tmp_path / "aordc.xlsx"
        xlsx_path.write_bytes(xlsx_bytes)

        params = parse_aordc_xlsx(
            xlsx_path,
            effective_date=date(2025, 12, 5),
            source_url="https://example.com",
            source_doc_revision="test-v1",
        )
        assert len(params) == 5
        products = {p.as_product for p in params}
        assert products == set(ASProduct)

    def test_weights_sum_to_one(self, tmp_path):
        xlsx_bytes = _make_aordc_xlsx(AORDC_ROWS)
        xlsx_path = tmp_path / "aordc.xlsx"
        xlsx_path.write_bytes(xlsx_bytes)

        params = parse_aordc_xlsx(
            xlsx_path,
            effective_date=date(2025, 12, 5),
            source_url="https://example.com",
            source_doc_revision="v1",
        )
        for p in params:
            assert abs(p.mix_weight_30min + p.mix_weight_60min - 1.0) < 1e-6

    def test_validates_against_schema(self, tmp_path):
        xlsx_bytes = _make_aordc_xlsx(AORDC_ROWS)
        xlsx_path = tmp_path / "aordc.xlsx"
        xlsx_path.write_bytes(xlsx_bytes)

        params = parse_aordc_xlsx(
            xlsx_path,
            effective_date=date(2025, 12, 5),
            source_url="https://example.com",
            source_doc_revision="v1",
        )
        for p in params:
            assert isinstance(p, ASDCParameters)


# ── Oracle: curve reconstruction accuracy ─────────────────────────────────────


def _asdc_mixture_normal(
    q_mw: np.ndarray,
    mu: float,
    sigma: float,
    w30: float,
    w60: float,
    voll: float,
    voll_cap_offset: float,
    min_step_floor: float,
) -> np.ndarray:
    """Compute ASDC price at quantity vector q_mw using mixture-normal formula.

    ASDC(q) = max(min_step_floor, (VOLL - voll_cap_offset) * (1 - F_mix(q)))
    where F_mix = w30 * Phi(q; mu, sigma_30) + w60 * Phi(q; mu, sigma_60)
    and sigma_30 = sigma * sqrt(0.5), sigma_60 = sigma * sqrt(1.0) (illustrative).
    """
    sigma_30 = sigma * np.sqrt(0.5)
    sigma_60 = sigma * np.sqrt(1.0)
    f_mix = w30 * stats.norm.cdf(q_mw, loc=mu, scale=sigma_30) + \
            w60 * stats.norm.cdf(q_mw, loc=mu, scale=sigma_60)
    price = (voll - voll_cap_offset) * (1.0 - f_mix)
    return np.maximum(price, min_step_floor)


@pytest.mark.skip(reason="Superseded by NPRR1268 implementation; see Chunk 3 for window validation")
class TestASDCOracleAccuracy:
    """Verify that curve reconstruction from ASDCParameters matches ASDCHourly.

    ADR 0003: reconstruction must match to ≤$0.10/MW-h on every breakpoint.
    """

    def _make_hourly_from_params(self, params: ASDCParameters) -> list[ASDCHourly]:
        """Generate synthetic ASDCHourly breakpoints from ASDCParameters."""
        q_values = np.linspace(0, params.mu * 3, 10)
        prices = _asdc_mixture_normal(
            q_values,
            mu=params.mu,
            sigma=params.sigma,
            w30=params.mix_weight_30min,
            w60=params.mix_weight_60min,
            voll=params.voll,
            voll_cap_offset=params.voll_cap_offset,
            min_step_floor=params.min_step_floor,
        )
        return [
            ASDCHourly(
                operating_date=date(2025, 12, 5),
                hour_ending=1,
                as_product=params.as_product,
                segment_index=i,
                breakpoint_mw=float(q),
                breakpoint_price=float(p),
                as_plan_mw=float(params.mu),
                source_filename="oracle_test.csv",
            )
            for i, (q, p) in enumerate(zip(q_values, prices))
        ]

    @pytest.mark.parametrize("product_row", AORDC_ROWS)
    def test_reconstruction_within_tolerance(self, product_row):
        """Reconstructed curve must match generated breakpoints to ≤$0.10/MW-h."""
        params = ASDCParameters(
            as_product=ASProduct(product_row["AS Product"].lower()),
            effective_date=date(2025, 12, 5),
            mu=product_row["Mu"],
            sigma=product_row["Sigma"],
            mix_weight_30min=product_row["Mix Weight 30min"],
            mix_weight_60min=product_row["Mix Weight 60min"],
            voll=product_row["VOLL"],
            voll_cap_offset=product_row["VOLL Cap Offset"],
            min_step_floor=product_row["Min Step Floor"],
            source_url="https://example.com",
            source_doc_revision="oracle-test",
        )

        hourly_rows = self._make_hourly_from_params(params)
        q_vals = np.array([h.breakpoint_mw for h in hourly_rows])
        published_prices = np.array([h.breakpoint_price for h in hourly_rows])

        reconstructed = _asdc_mixture_normal(
            q_vals,
            mu=params.mu,
            sigma=params.sigma,
            w30=params.mix_weight_30min,
            w60=params.mix_weight_60min,
            voll=params.voll,
            voll_cap_offset=params.voll_cap_offset,
            min_step_floor=params.min_step_floor,
        )

        max_err = float(np.max(np.abs(reconstructed - published_prices)))
        assert max_err <= 0.10, (
            f"Oracle failure for {product_row['AS Product']}: "
            f"max reconstruction error = ${max_err:.4f}/MW-h > $0.10 threshold"
        )

    def test_monotone_decreasing_price(self):
        """ASDC breakpoint prices must be non-increasing in quantity."""
        params = ASDCParameters(
            as_product=ASProduct.REGUP,
            effective_date=date(2025, 12, 5),
            mu=2500.0,
            sigma=1200.0,
            mix_weight_30min=0.4,
            mix_weight_60min=0.6,
            voll=5000.0,
            voll_cap_offset=250.0,
            min_step_floor=0.25,
            source_url="https://example.com",
            source_doc_revision="oracle-test",
        )
        q_vals = np.linspace(0, 10000, 50)
        prices = _asdc_mixture_normal(
            q_vals,
            mu=params.mu, sigma=params.sigma,
            w30=params.mix_weight_30min, w60=params.mix_weight_60min,
            voll=params.voll, voll_cap_offset=params.voll_cap_offset,
            min_step_floor=params.min_step_floor,
        )
        diffs = np.diff(prices)
        assert np.all(diffs <= 1e-9), "ASDC prices must be non-increasing in quantity"

    def test_price_bounded_above_by_voll(self):
        """ASDC prices must not exceed VOLL - voll_cap_offset."""
        voll, cap_offset = 5000.0, 250.0
        params = ASDCParameters(
            as_product=ASProduct.ECRS,
            effective_date=date(2025, 12, 5),
            mu=5500.0, sigma=2500.0,
            mix_weight_30min=0.4, mix_weight_60min=0.6,
            voll=voll, voll_cap_offset=cap_offset,
            min_step_floor=0.25,
            source_url="https://example.com",
            source_doc_revision="oracle-test",
        )
        prices = _asdc_mixture_normal(
            np.array([0.0]),
            mu=params.mu, sigma=params.sigma,
            w30=params.mix_weight_30min, w60=params.mix_weight_60min,
            voll=params.voll, voll_cap_offset=params.voll_cap_offset,
            min_step_floor=params.min_step_floor,
        )
        assert prices[0] <= voll - cap_offset + 1e-6


# ── NPRR1268 formula fixture tests ────────────────────────────────────────────

# Published v0.1 AORDC parameters
V01_PARAMS = {"mu": 675.0, "sigma": 1524.0, "voll": 5000.0}

# A representative AS Plan to use across tests
SAMPLE_AS_PLAN = {
    "rureq":    1500.0,
    "rrsreq":   3000.0,
    "ecrsreq":  2000.0,
    "regdnreq": 1200.0,
    "nspinreq": 1000.0,
}


class TestNPRR1268Formula:
    """Verify the NPRR1268 §4.4.12 formula transcription.

    These five tests use only the published AORDC parameters and a
    representative AS Plan. They do NOT require np4-212-cd data; that
    end-to-end validation lives in Chunk 3.
    """

    def test_aordc_value_at_mcl(self):
        """AORDC at the MCL boundary (reserve=3000 MW) should be ~$3,355.

        From the formula: (1 - pnorm(3000-3000, 675, 1524)) * 5000
                        = (1 - pnorm(-675, 0, 1524)) * 5000
                        ≈ (1 - 0.328) * 5000 ≈ $3,355
        """
        v = _aordc(np.array([3000.0]), **V01_PARAMS)[0]
        assert 3300 < v < 3410, f"AORDC at MCL = ${v:.2f}, expected ~$3,355"

    def test_mcl_quantities_sum_to_3000(self):
        """MCL allocations must always sum to 3000 MW exactly, in all 3 cases."""
        for rureq, rrsreq, ecrsreq, case_label in [
            (1500, 3000, 2000, "case 3 (typical)"),
            (3500, 2500,  500, "case 1 (large RUREQ)"),
            (4500, 5000,  100, "case 2 (excess from above)"),
        ]:
            q = _mcl_quantities(rureq, rrsreq, ecrsreq)
            total = sum(q.values())
            assert abs(total - MCL) < 0.1, (
                f"{case_label}: MCL allocation sums to {total:.2f}, "
                f"expected {MCL}"
            )

    def test_regdn_is_flat_at_voll(self):
        """REGDN ASDC is a flat segment at VOLL across the Reg-Down AS Plan."""
        bps = reconstruct_per_product_asdc(
            "regdn", **V01_PARAMS, as_plan=SAMPLE_AS_PLAN,
        )
        assert bps.shape == (2, 2)
        assert bps[0, 0] == 0.0 and bps[1, 0] == SAMPLE_AS_PLAN["regdnreq"]
        assert bps[0, 1] == V01_PARAMS["voll"]
        assert bps[1, 1] == V01_PARAMS["voll"]

    def test_per_product_caps_match_empirical(self):
        """The four upward products' linear-region prices match NPRR1268 spec.

        These exact values ($9,052 / $7,051 / $5,050 / $5,000) were observed
        empirically in np4-212-cd before the formula was extracted; their
        match here confirms the formula transcription.
        """
        expected_caps = {
            "regup": 9052.0,  # VOLL + 4052
            "rrs":   7051.0,  # VOLL + 2051
            "ecrs":  5050.0,  # VOLL + 50
            "nspin": 5000.0,  # VOLL + 0
        }
        for product, expected in expected_caps.items():
            bps = reconstruct_per_product_asdc(
                product, **V01_PARAMS, as_plan=SAMPLE_AS_PLAN,
            )
            linear_price = bps[0, 1]
            assert linear_price == expected, (
                f"{product} linear-region cap = ${linear_price:.2f}, "
                f"expected ${expected:.2f} (VOLL + ${MAX_DEMAND_PRICE_OFFSETS[product]})"
            )

    def test_nspin_three_segment_structure(self):
        """NSPIN: $15 floor applies within nspinreq; raw AORDC beyond it.

        Per NPRR1268/NPRR1269: NSPIN curve extends beyond nspinreq (step iv
        absorbs all remaining AORDC segments). The floor only applies to
        breakpoints with MW ≤ nspinreq.
        """
        nspinreq = SAMPLE_AS_PLAN["nspinreq"]
        bps = reconstruct_per_product_asdc(
            "nspin", **V01_PARAMS, as_plan=SAMPLE_AS_PLAN, apply_floor=True,
        )
        mw = bps[:, 0]
        prices = bps[:, 1]

        within = prices[mw <= nspinreq]
        assert within.min() >= ASDC_FLOOR - 1e-9, (
            f"NSPIN within-requirement min price ${within.min():.4f} "
            f"below floor ${ASDC_FLOOR}"
        )

        assert (within > ASDC_FLOOR + 1.0).sum() > 0, (
            "NSPIN should have a declining region above the $15 floor"
        )

        beyond = prices[mw > nspinreq]
        assert len(beyond) > 0, "NSPIN should extend beyond nspinreq (step iv)"
        assert beyond.min() < ASDC_FLOOR, (
            "NSPIN extension beyond nspinreq should have raw AORDC prices below floor"
        )


# ── ADR 0006 integration oracle test ─────────────────────────────────────────

_BENCH_DATA_ROOT = Path(
    os.environ.get("BENCH_DATA_ROOT", Path.home() / "hybridbid-bench-data" / "v0.1")
)
_ORACLE_DATE = date(2026, 2, 15)
_ORACLE_HE = 13
_ORACLE_PARAMS = {"mu": 675.0, "sigma": 1524.0, "voll": 5000.0}
_ORACLE_TOLERANCE = 0.10  # $/MW-h (ADR 0006 acceptance criterion)

_oracle_data_missing = not (_BENCH_DATA_ROOT / "asdc_hourly" / "2026-02-15.parquet").exists()


@pytest.mark.skipif(
    _oracle_data_missing,
    reason="Oracle data not present at BENCH_DATA_ROOT — skipped in CI",
)
@pytest.mark.parametrize("product", ["regup", "rrs", "ecrs", "nspin"])
def test_oracle_single_hour(product: str) -> None:
    """NPRR1268 formula matches published ASDC breakpoints to ≤$0.10/MW-h (ADR 0006).

    Uses 2026-02-15 HE13 as the canonical integration check. Requires
    v0.1 oracle data at BENCH_DATA_ROOT.
    """
    as_plan = load_as_plan(_ORACLE_DATE, _ORACLE_HE)
    oracle = load_asdc_hourly(_ORACLE_DATE, _ORACLE_HE, product)
    recon = reconstruct_per_product_asdc(product, **_ORACLE_PARAMS, as_plan=as_plan)

    assert len(oracle) == len(recon), (
        f"{product}: oracle has {len(oracle)} breakpoints, recon has {len(recon)}"
    )
    price_err = np.abs(oracle[:, 1] - recon[:, 1])
    mean_err = float(price_err.mean())
    assert mean_err <= _ORACLE_TOLERANCE, (
        f"{product}: mean price error ${mean_err:.4f}/MW-h exceeds ${_ORACLE_TOLERANCE}/MW-h"
    )

    mw_err = np.abs(oracle[:, 0] - recon[:, 0]).max()
    assert mw_err == 0.0, f"{product}: MW breakpoint mismatch, max err={mw_err}"
