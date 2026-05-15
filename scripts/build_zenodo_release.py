"""Package v0.1 for Zenodo release.

Produces ercot-rtcb-bench-v0.1.zip in the repo root, ready for manual
upload to Zenodo. Data is sourced from two locations:
  - ~/hybridbid-bench-data/v0.1/   (rt_prices, as_clearing, dam_prices,
                                     system_conditions, asdc_hourly)
  - data/processed/v0.1/           (as_plan/, asdc_params.parquet)

Usage:
    python scripts/build_zenodo_release.py
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DATA_ROOT = Path(
    os.environ.get("BENCH_DATA_ROOT", Path.home() / "hybridbid-bench-data" / "v0.1")
)
STAGE = REPO_ROOT / "build" / "zenodo_v0.1"
ZIP_OUT = REPO_ROOT / "ercot-rtcb-bench-v0.1.zip"


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def main() -> None:
    # Verify sources exist before touching anything
    missing = []
    for name in ["rt_prices", "as_clearing", "dam_prices", "system_conditions", "asdc_hourly"]:
        p = BENCH_DATA_ROOT / name
        if not p.exists():
            missing.append(str(p))
    for name in ["as_plan", "asdc_params.parquet"]:
        p = REPO_ROOT / "data" / "processed" / "v0.1" / name
        if not p.exists():
            missing.append(str(p))
    if missing:
        print("ERROR: Missing data sources:")
        for m in missing:
            print(f"  {m}")
        raise SystemExit(1)

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    # Top-level files
    _copy(REPO_ROOT / "LICENSE",       STAGE / "LICENSE")
    _copy(REPO_ROOT / "CITATION.cff",  STAGE / "CITATION.cff")
    _copy(REPO_ROOT / "docs" / "zenodo_release_readme.md", STAGE / "README.md")

    # Docs
    _copy(REPO_ROOT / "docs" / "dataset-card.md",  STAGE / "docs" / "dataset-card.md")
    _copy(REPO_ROOT / "docs" / "decisions",         STAGE / "docs" / "decisions")
    for fn in ["v0_1_report.md", "v0_1_coverage_notes.md", "asdc_oracle_summary.md"]:
        src = REPO_ROOT / "data" / "validation" / fn
        if src.exists():
            _copy(src, STAGE / "docs" / "validation" / fn)

    # Data — external tables
    dst_data = STAGE / "data" / "v0.1"
    for name in ["rt_prices", "as_clearing", "dam_prices", "system_conditions", "asdc_hourly"]:
        _copy(BENCH_DATA_ROOT / name, dst_data / name)

    # Data — repo tables
    _copy(REPO_ROOT / "data" / "processed" / "v0.1" / "as_plan",
          dst_data / "as_plan")
    _copy(REPO_ROOT / "data" / "processed" / "v0.1" / "asdc_params.parquet",
          dst_data / "asdc_params.parquet")

    # Build ZIP
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    n_files = 0
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(STAGE))
                n_files += 1

    size_mb = ZIP_OUT.stat().st_size / 1024 / 1024
    print(f"Built: {ZIP_OUT.name}")
    print(f"Size:  {size_mb:.1f} MB")
    print(f"Files: {n_files}")
    print()
    print("Contents summary:")
    with zipfile.ZipFile(ZIP_OUT) as zf:
        names = zf.namelist()
    for prefix in ["README", "LICENSE", "CITATION", "docs/", "data/"]:
        matching = [n for n in names if n.startswith(prefix)]
        print(f"  {prefix}: {len(matching)} entries")


if __name__ == "__main__":
    main()
