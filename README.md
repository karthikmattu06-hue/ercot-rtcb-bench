# ercot-rtcb-bench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20204993.svg)](https://doi.org/10.5281/zenodo.20204993)

An open benchmark for battery energy storage bidding under ERCOT's
Real-Time Co-optimization Plus Batteries (RTC+B) market design,
which went live on December 5, 2025.

## Status: 🚧 Active development

Latest completed work: W7 (Fern-exclusion sensitivity, Exhibit-2 basis
correction, ADR 0018). Decision records through 0019 are in
[`docs/decisions/`](docs/decisions/).

This repository accompanies the forthcoming workshop paper
"Post-RTC+B Operator Toolkit: An Open Benchmark and Reference
Bidding Stack for ERCOT 6-D Co-optimized Markets" (in preparation,
target venue: NeurIPS 2026 Climate Change AI workshop).

## What's here

- **Versioned datasets** of post-RTC+B ERCOT market data (prices,
  ASDC parameters, AS clearing quantities for all five AS products),
  published on Zenodo with DOIs.
- **Five reference bidding implementations**, all linear programs over the
  6-D co-optimized action space:
  1. Perfect-foresight LP — non-causal upper bound
  2. Deterministic LP on a DAM-broadcast point forecast, rolling-horizon
  3. EV-deterministic LP (probability-weighted scenario mean), rolling-horizon
  4. Two-stage stochastic LP over a scenario tree, rolling-horizon
  5. Decision-focused learning — an MLP forecaster trained through a
     differentiable LP layer (`cvxpylayers`)
- **Backtest scripts** in [`scripts/`](scripts/) that run rolling-horizon
  evaluations on fixed panels and write results plus a JSON audit record
  under `data/audit/`.
- **Architecture decision records** documenting every methodological choice,
  including the two measured improvements that were built and then retired
  after pre-registered replication (ADR 0014, 0015).

### Terminology note

Earlier versions of this README described these methods as "MIP" and "MILP."
That was a misnomer: **no binary or integer variables appear in any of the
bidding formulations** — they are pure LPs. The naming was corrected in
[ADR 0008](docs/decisions/0008-w3c-stochastic-lp.md). The generic solver
interface in `methods/solver.py` does support integrality, but no method here
uses it. Two file names predate the correction and still carry the old label
(`tests/test_milp_baseline.py`, `scripts/smoke_milp.py`); their contents are LPs.

## Not implemented yet

Stated plainly so the repository is not read as claiming more than it contains:

- **Reinforcement learning.** `src/ercot_rtcb_bench/envs/` is an empty package
  stub. There is no Gymnasium environment, no SAC implementation, and no RL
  dependency in `pyproject.toml`. A constraint-aware RL baseline is planned,
  not shipped. (A separate deep-RL study on this problem lives in
  [hybridbid](https://github.com/karthikmattu06-hue/hybridbid).)
- **A library-level evaluation harness.** `src/ercot_rtcb_bench/eval/` is a
  stub; evaluation currently lives in the per-panel scripts under `scripts/`.
- **v1.0 dataset.** In preparation; v0.2 is the current canonical target.

## Quickstart

```bash
# 1. Install (Python 3.11+)
git clone https://github.com/karthikmattu06-hue/ercot-rtcb-bench.git
cd ercot-rtcb-bench
pip install -e ".[dev,solvers]"

# 2. Get the canonical dataset (v0.2) from Zenodo
#    https://doi.org/10.5281/zenodo.21178739
#    Unpack the parquets under data/ as described in data/README.md

# 3. Run the W3-C comparison: perfect-foresight LP vs the three causal LPs
python scripts/backtest_w3c.py
```

The W3-C run prints a comparison table and writes
`docs/results_w3c.md` plus `data/audit/backtest_w3c.json`.

Note on the reference number: the committed `docs/results_w3c.md` table is a
**pre-repin vintage** (Stochastic LP $238,376). The canonical Stochastic-LP
evaluation baseline against dataset **v0.2** is **$238,378.80** — the ADR 0013
re-pinned value, recorded in `data/audit/w5r_run.json` (`eval_baseline_repinned`).
Compare a fresh v0.2 run against the re-pinned value, not the committed table.

To run the decision-focused learning method, install its extra as well:

```bash
pip install -e ".[dev,solvers,dfl]"
python scripts/backtest_w3d.py
```

Gurobi is used when `gurobipy` is importable and licensed, and the solver
falls back to HiGHS and then SciPy. Results in this repository were produced
with Gurobi.

## Dataset

Concept DOI (always resolves to the latest version): [10.5281/zenodo.20204993](https://doi.org/10.5281/zenodo.20204993)

**v0.2** (Jan 1 – Jun 9, 2026) — **canonical reproduction target**: [10.5281/zenodo.21178739](https://doi.org/10.5281/zenodo.21178739)  
Canonical forecaster-input parquets (RT LMP + AS MCPC, DAM SPP + AS MCPC, system
conditions) re-pinned to the ADR 0013 rebuild + W5-R backfill pull. The committed
baseline/audit numbers reproduce against **v0.2** (Stochastic-LP eval baseline
$238,378.80); see [`docs/decisions/0016-zenodo-v02-deposit.md`](docs/decisions/0016-zenodo-v02-deposit.md).
v0.2 is **not** a strict superset of v0.1 — it drops the Dec 2025 span and the auxiliary
tables (`as_clearing`, `asdc_hourly`, `asdc_params`, `as_plan`) and rebuilds overlapping
months; use v0.1 for those.

**v0.1** (Dec 5, 2025 – Mar 31, 2026) — historical: [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20204994.svg)](https://doi.org/10.5281/zenodo.20204994)  
**v1.0** (Dec 5, 2025 – Jun 5, 2026): in preparation.

See [`docs/dataset-card.md`](docs/dataset-card.md) for full documentation.

## Scope and limitations

- The evidence window is **early RTC+B (Dec 2025 – Jun 2026)**. Seasonal
  generalization was tested on a mild July (ADR 0017, `scripts/w6_seasonal.py`)
  and should not be assumed beyond that bound.
- Single-node price-taker assumption; no network model.
- Two measured forecast-error corrections were built, evaluated, and **retired**
  after pre-registered multi-panel replication showed them net-negative
  out-of-sample (ADR 0014, 0015). They are documented rather than shipped.

## Writing

- [Post #1: What RTC+B Actually Changed — A Visual Walkthrough of the 6-D Action Space](https://karthik204653.substack.com/p/what-rtcb-actually-changed-a-walkthrough) (2026-05-14)
- [Post #2: The $58k That Wasn't](https://karthik204653.substack.com/p/the-58k-that-wasnt) (2026-08-10) — two measured forecast-error levers, both retired under pre-registered replication (ADR 0014, 0015)

## Repository structure

```
src/ercot_rtcb_bench/
  data/         Dataset loading, validation, and fetch
  markets/      RTC+B market model (6-D action space, ASDC, AS products)
  methods/      Bidding methods: perfect_foresight, point_forecast,
                rolling_lp, stochastic_lp, dfl/
  forecaster/   Scenario generation and point forecasters
  envs/         Package stub — Gymnasium environments not yet implemented
  eval/         Package stub — evaluation currently lives in scripts/
scripts/        Data fetch and per-panel backtest scripts
docs/           Dataset card, primers, architecture decision records
tests/          Unit and integration tests
data/           NOT committed — see data/README.md for access
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
