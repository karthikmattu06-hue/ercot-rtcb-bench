# Contributing

## Branching model

Trunk-based development with short-lived feature branches.

- `main` is the stable branch. CI must pass before merge.
- Feature branches: `feat/<slug>`, e.g. `feat/milp-baseline`
- Data branches: `data/<slug>`, e.g. `data/v1_0-backfill`
- Branch lifetime: ideally under 1 week. If it lives longer, rebase on `main` regularly.

No direct commits to `main`. Open a PR; squash-merge when approved.

## Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add deterministic MILP baseline
fix: correct UTC timezone handling in transform
docs: expand dataset card with ASDC note
data: add v0.1 validation report
chore: update pre-commit hooks to ruff 0.4
test: add coverage for ASClearing negative MCPC tolerance
```

No "wip", "stuff", "minor", or "fix fix" commits on `main`. Squash before merging.

## Running tests locally

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run linting
ruff check src/ tests/
black --check src/ tests/
mypy src/
```

## Data workflow

Raw and processed data are NOT committed to the repo. To reproduce locally:

```bash
# 1. Set credentials
cp .env.example .env  # then fill in ERCOT API keys

# 2. Fetch raw data (v0.1)
bash scripts/fetch_v0_1.sh

# 3. Build canonical Parquet tables and run validation
python scripts/build_v0_1.py

# 4. Check validation report
cat data/validation/v0_1_report.md
```

The v0.1 Parquet files should be placed at `~/hybridbid-bench-data/v0.1/`
(outside the repo). Zenodo upload happens when the schema is locked.

## Adding a new method

1. Create `src/ercot_rtcb_bench/methods/<method_name>.py`
2. Add unit tests in `tests/test_<method_name>.py`
3. Benchmark results go in `results/<method_name>/`
4. Document the method in `docs/methods/<method_name>.md`

Methods must be reproducible: random seeds in config, all hyperparameters logged.
