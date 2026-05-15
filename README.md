# ercot-rtcb-bench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20204994.svg)](https://doi.org/10.5281/zenodo.20204994)

An open benchmark for battery energy storage bidding under ERCOT's
Real-Time Co-optimization Plus Batteries (RTC+B) market design,
which went live on December 5, 2025.

## Status: 🚧 Active development (Summer 2026)

This repository accompanies the forthcoming workshop paper
"Post-RTC+B Operator Toolkit: An Open Benchmark and Reference
Bidding Stack for ERCOT 6-D Co-optimized Markets" (in preparation,
target venue: NeurIPS 2026 Climate Change AI workshop).

## What's here

- **Versioned datasets** of post-RTC+B ERCOT market data (prices,
  ASDC parameters, AS clearing quantities for all five AS products).
- **Reference bidding implementations**: perfect-foresight MIP,
  deterministic MILP with point forecasts, two-stage stochastic MILP,
  constraint-aware SAC, and decision-focused learning baselines.
- **Evaluation harness** for rolling-horizon backtesting with realistic
  data partitioning.

## Quickstart

(Coming soon — Week 4)

## Dataset

**v0.1** (Dec 5, 2025 – Mar 31, 2026): [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20204994.svg)](https://doi.org/10.5281/zenodo.20204994)  
**v1.0** (Dec 5, 2025 – Jun 5, 2026): in preparation.

See [`docs/dataset-card.md`](docs/dataset-card.md) for full documentation.

## Writing

- [Post #1: What RTC+B Actually Changed — A Visual Walkthrough of the 6-D Action Space](https://substack.com/@karthik204653) (2026-05-14)

## Repository structure

```
src/ercot_rtcb_bench/   Core library (data, markets, envs, methods, eval)
scripts/                Reproducible data fetch scripts
docs/                   Dataset card, primers, architecture decision records
tests/                  Unit and integration tests
data/                   NOT committed — see data/README.md for access
notebooks/exploratory/  Scratchpads only, not deliverables
```

## Development

```bash
# Install (Python 3.11+)
pip install -e ".[dev]"

# Run tests
pytest tests/

# Lint
ruff check src/ tests/
black --check src/ tests/
mypy src/
```

## Citation

If you use this benchmark in academic work, please cite via the
`CITATION.cff` file in this repository.

## License

Code: Apache-2.0 (see `LICENSE`).
Data: Derived from ERCOT public data products under their respective
terms; see `docs/dataset-card.md` for details.
