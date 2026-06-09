"""W3-D DFL backtest: MLP + differentiable LP, Apr 20-26 2026 panel.

Phases:
  check  (default) -- Task 0 deps + Task 1 diff-LP verify + Task 3 single-day overfit
  train             -- Task 4 full training (run AFTER reviewing Task 3 results)
  eval              -- Task 5 five-method table (run AFTER training completes)

Usage:
  python scripts/backtest_w3d.py                 # phase=check
  python scripts/backtest_w3d.py --phase train
  python scripts/backtest_w3d.py --phase eval
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.dfl import (
    FEATURE_DIM,
    EPS,
    T_TRAIN,
    BESSQPLayer,
    FeatureNormalizer,
    PriceResidualMLP,
    extract_features,
)
from ercot_rtcb_bench.methods.dfl.eval import eval_panel
from ercot_rtcb_bench.methods.dfl.train import run_training
from ercot_rtcb_bench.methods.perfect_foresight import _PRICE_COLS, perfect_foresight
from ercot_rtcb_bench.methods.rolling_lp import T1, T2

# ── Constants ─────────────────────────────────────────────────────────────────
PANEL_START = pd.Timestamp("2026-04-20", tz="UTC")
PANEL_END   = pd.Timestamp("2026-04-27", tz="UTC")

TRAIN_START = date(2026, 1,  9)
TRAIN_END   = date(2026, 4, 14)  # exclusive
VAL_START   = date(2026, 4, 14)
VAL_END     = date(2026, 4, 20)  # exclusive (Apr 14–19)
OVERFIT_DAY = date(2026, 3, 15)  # single-day overfit check

BESS = BESSParams.default_100mw_4hr()

CHECKPOINT_DIR  = Path("data/checkpoints")
NORMALIZER_PATH = CHECKPOINT_DIR / "dfl_normalizer.npz"
AUDIT_DIR       = Path("data/audit")

# W3-C baseline numbers (for comparison table)
_PF_ROW  = dict(total=351612, energy=253765, as_rev=97601, liq=245)
_DET_ROW = dict(total=238421, energy=185034, as_rev=47871, liq=5516)
_EV_ROW  = dict(total=250174, energy=168703, as_rev=73412, liq=8058)
_STOCH_ROW = dict(total=238376, energy=159021, as_rev=72478, liq=6878)


# ── Task 0 ────────────────────────────────────────────────────────────────────

def task_0_deps() -> None:
    print("\n=== Task 0: Dependency check ===")
    import cvxpy; print(f"  cvxpy       {cvxpy.__version__}")
    import cvxpylayers; print(f"  cvxpylayers {cvxpylayers.__version__}")
    import diffcp; print(f"  diffcp      {diffcp.__version__}")
    print(f"  torch       {torch.__version__}")
    print(f"  BESS: {BESS.power_mw:.0f} MW / {BESS.energy_mwh:.0f} MWh, "
          f"RTE={BESS.rte}, NSPIN_h={BESS.nspin_soc_hours}")
    print(f"  FEATURE_DIM={FEATURE_DIM}, T_TRAIN={T_TRAIN}, EPS={EPS}")
    print("  Task 0 OK")


# ── Task 1 ────────────────────────────────────────────────────────────────────

def task_1_verify_layer(dataset: ForecasterDataset) -> None:
    """Compare diff-LP against Gurobi LP on the same T=72 input."""
    print("\n=== Task 1: Diff-LP vs Gurobi LP verification ===")
    sample_day = date(2026, 3, 15)
    dam = dataset.get_dam_array(sample_day)  # (6, 288)
    prices_72 = dam[:, :T_TRAIN].astype(np.float64)  # first 6h

    s0_val = BESS.soc_energy_init  # 200 MWh

    # ── Gurobi LP (via perfect_foresight on T=72 intervals) ──────────────────
    idx_72 = pd.date_range("2026-03-15", periods=T_TRAIN, freq="5min", tz="UTC")
    prices_df = pd.DataFrame(
        prices_72.T,
        index=idx_72,
        columns=_PRICE_COLS,
    )
    import copy
    bess_copy = copy.copy(BESS)
    bess_copy.soc_init = s0_val / BESS.energy_mwh
    t0 = time.perf_counter()
    pf_result = perfect_foresight(bess_copy, prices_df, terminal_lmp=0.0)
    gurobi_time = time.perf_counter() - t0
    gurobi_d = pf_result.dispatch["discharge_mw"].values[:T1]
    gurobi_c = pf_result.dispatch["charge_mw"].values[:T1]
    gurobi_as = pf_result.dispatch[
        ["award_regup_mw", "award_regdn_mw", "award_rrs_mw",
         "award_ecrs_mw", "award_nspin_mw"]
    ].values[:T1]

    print(f"  Gurobi LP (T=72): obj={pf_result.revenue_total:.2f}, "
          f"solve={gurobi_time:.3f}s")

    # ── Diff-LP (BESSQPLayer, per-unit) ──────────────────────────────────────
    layer = BESSQPLayer(BESS, T=T_TRAIN, eps=EPS)

    lmp_t        = torch.tensor(prices_72[0], dtype=torch.float32)
    mcpc_ru_t    = torch.tensor(prices_72[1], dtype=torch.float32)
    mcpc_rd_t    = torch.tensor(prices_72[2], dtype=torch.float32)
    mcpc_rrs_t   = torch.tensor(prices_72[3], dtype=torch.float32)
    mcpc_ecrs_t  = torch.tensor(prices_72[4], dtype=torch.float32)
    mcpc_ns_t    = torch.tensor(prices_72[5], dtype=torch.float32)
    s0_t   = torch.tensor(s0_val, dtype=torch.float32)
    term_t = torch.tensor(0.0,    dtype=torch.float32)

    t0 = time.perf_counter()
    d_t, c_t, a_ru_t, a_rd_t, a_rrs_t, a_ecrs_t, a_ns_t, s_t = layer(
        lmp_t, mcpc_ru_t, mcpc_rd_t, mcpc_rrs_t, mcpc_ecrs_t, mcpc_ns_t,
        s0_t, term_t,
        solver_args={"max_iters": 10000, "eps": 1e-6},
    )
    qp_time = time.perf_counter() - t0

    # Full-horizon arrays (MW / MWh) — for constraint check
    d_full   = d_t.detach().numpy()
    c_full   = c_t.detach().numpy()
    a_ru_f   = a_ru_t.detach().numpy()
    a_rd_f   = a_rd_t.detach().numpy()
    a_rrs_f  = a_rrs_t.detach().numpy()
    a_ecrs_f = a_ecrs_t.detach().numpy()
    a_ns_f   = a_ns_t.detach().numpy()
    s_full   = s_t.detach().numpy()     # length T+1

    # Constraint violations (physical units)
    P  = BESS.power_mw
    E  = BESS.energy_mwh
    dt = BESS.dt_hours
    rte = BESS.rte

    viol_nonneg   = -min(d_full.min(), c_full.min(), a_ru_f.min(), a_rd_f.min(),
                         a_rrs_f.min(), a_ecrs_f.min(), a_ns_f.min(), 0.0)
    viol_disc     = max(0.0, (d_full + a_ru_f + a_rrs_f + a_ecrs_f + a_ns_f - P).max())
    viol_chg      = max(0.0, (c_full + a_rd_f - P).max())
    viol_soc_lo   = max(0.0, (BESS.soc_energy_min - s_full).max())
    viol_soc_hi   = max(0.0, (s_full - E).max())
    dyn_err       = abs(s_full[1:] - (s_full[:-1] - dt * d_full + dt * rte * c_full)).max()
    nspin_viol    = max(0.0, (BESS.nspin_soc_hours * a_ns_f - s_full[:T_TRAIN]).max())

    print(f"  Diff-LP (T=72, ε={EPS}): solve={qp_time:.3f}s")
    print(f"  Constraint violations (≤ 1e-3 MW/MWh is acceptable):")
    print(f"    Non-negativity:     {viol_nonneg:.2e} MW")
    print(f"    Discharge side:     {viol_disc:.2e} MW  (P={P:.0f} MW)")
    print(f"    Charge side:        {viol_chg:.2e} MW")
    print(f"    SoC lower bound:    {viol_soc_lo:.2e} MWh")
    print(f"    SoC upper bound:    {viol_soc_hi:.2e} MWh")
    print(f"    SoC dynamics err:   {dyn_err:.2e} MWh")
    print(f"    NSPIN SoC:          {nspin_viol:.2e} MWh")

    max_viol_mw  = max(viol_nonneg, viol_disc, viol_chg)
    max_viol_mwh = max(viol_soc_lo, viol_soc_hi, dyn_err, nspin_viol)
    if max_viol_mw > 0.1 or max_viol_mwh > 0.5:
        print(f"\n  HARD STOP: constraint violations exceed tolerance — "
              f"max MW viol={max_viol_mw:.3f}, max MWh viol={max_viol_mwh:.3f}")
        sys.exit(1)

    # Settlement comparison (first hour, both methods)
    qp_d  = d_full[:T1]
    qp_c  = c_full[:T1]
    qp_as = np.stack([a_ru_f[:T1], a_rd_f[:T1], a_rrs_f[:T1],
                      a_ecrs_f[:T1], a_ns_f[:T1]], axis=1)

    gurobi_rev = float(
        (prices_72[0, :T1] * (gurobi_d - gurobi_c) * dt).sum()
        + (prices_72[1:, :T1] * gurobi_as.T * dt).sum()
    )
    qp_rev = float(
        (prices_72[0, :T1] * (qp_d - qp_c) * dt).sum()
        + (prices_72[1:, :T1] * qp_as.T * dt).sum()
    )

    print(f"\n  First-hour revenue: Gurobi=${gurobi_rev:.2f}  QP=${qp_rev:.2f}  "
          f"gap={abs(gurobi_rev - qp_rev) / max(abs(gurobi_rev), 1) * 100:.1f}%")

    d_max_diff  = abs(gurobi_d - qp_d).max()
    c_max_diff  = abs(gurobi_c - qp_c).max()
    as_max_diff = abs(gurobi_as - qp_as).max()
    print(f"  Max action divergence:  d={d_max_diff:.3f} MW  c={c_max_diff:.3f} MW  "
          f"AS={as_max_diff:.3f} MW")

    if abs(gurobi_rev - qp_rev) / max(abs(gurobi_rev), 1) > 0.15:
        print("  HARD STOP: QP revenue diverges from Gurobi LP by >15% — "
              "check cvxpylayers formulation.")
        sys.exit(1)
    else:
        print("  Task 1 OK — per-unit diff-LP: constraints clean, revenue within tolerance.")


# ── Task 3 ────────────────────────────────────────────────────────────────────

def task_3_single_day_overfit(dataset: ForecasterDataset) -> None:
    """100-step overfit on OVERFIT_DAY. Verifies gradient flow end-to-end."""
    print(f"\n=== Task 3: Single-day pipeline check ({OVERFIT_DAY}) ===")
    layer = BESSQPLayer(BESS, T=T_TRAIN, eps=EPS)

    # Build normalizer from a small subset (just OVERFIT_DAY itself — one sample, OK for check)
    raw_feat = extract_features(OVERFIT_DAY, dataset)
    norm = FeatureNormalizer()
    norm.fit([raw_feat])

    mlp = PriceResidualMLP(input_dim=FEATURE_DIM)
    optimizer = torch.optim.Adam(mlp.parameters(), lr=1e-3)

    from ercot_rtcb_bench.methods.dfl.train import _preload, _step
    cache = _preload([OVERFIT_DAY], dataset, norm)

    print("  Running 100 overfit steps...")
    losses: list[float] = []
    for step in range(100):
        mlp.train()
        optimizer.zero_grad()
        loss = _step(OVERFIT_DAY, cache, mlp, layer, BESS, T_TRAIN)
        if loss is None:
            print(f"  Solver failure at step {step} — HARD STOP.")
            sys.exit(1)
        loss.backward()

        if step == 0:
            # Report gradient norms
            total_norm = 0.0
            for p in mlp.parameters():
                if p.grad is not None:
                    total_norm += p.grad.data.norm(2).item() ** 2
            total_norm = total_norm ** 0.5
            print(f"  Step 0 gradient norm: {total_norm:.4f}")
            if total_norm < 1e-8:
                print("  HARD STOP: zero gradients — check formulation or ε.")
                sys.exit(1)

        torch.nn.utils.clip_grad_norm_(mlp.parameters(), max_norm=1.0)
        optimizer.step()
        losses.append(float(loss.detach()))

        if (step + 1) % 20 == 0:
            print(f"  Step {step+1:3d}: loss={losses[-1]:+.2f}  "
                  f"(running min={min(losses):.2f})")

    # Check monotonic decrease trend (compare first 20 vs last 20)
    first20_mean = float(np.mean(losses[:20]))
    last20_mean  = float(np.mean(losses[80:]))
    trend_ok = last20_mean < first20_mean

    print(f"\n  Overfit summary:")
    print(f"    Loss at step   1: {losses[0]:+.4f}")
    print(f"    Loss at step 100: {losses[-1]:+.4f}")
    print(f"    Mean steps 1-20:  {first20_mean:+.4f}")
    print(f"    Mean steps 81-100:{last20_mean:+.4f}")
    print(f"    Decreasing trend: {'YES' if trend_ok else 'NO (flat — possible gradient issue)'}")

    if not trend_ok:
        print("  WARNING: loss did not decrease — gradient signal may be weak.")
        print("  Possible causes: ε too small, all constraints inactive, feature NaN.")

    print("\n  Task 3 complete. Review the loss curve above before running --phase train.")
    print("  If trend is decreasing and gradient norm is non-zero, proceed.")


# ── Task 4 ────────────────────────────────────────────────────────────────────

def task_4_full_training(dataset: ForecasterDataset) -> dict:
    print("\n=== Task 4: Full training ===")
    train_days = dataset.available_days(TRAIN_START, TRAIN_END)
    val_days   = dataset.available_days(VAL_START,   VAL_END)
    print(f"  Train: {len(train_days)} days  ({train_days[0]} … {train_days[-1]})")
    print(f"  Val:   {len(val_days)} days  ({val_days[0]} … {val_days[-1]})")

    # Build normalizer on training features
    print("  Fitting feature normalizer...")
    raw_features = [extract_features(d, dataset) for d in train_days]
    norm = FeatureNormalizer()
    norm.fit(raw_features)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    norm.save(NORMALIZER_PATH)
    print(f"  Normalizer saved to {NORMALIZER_PATH}")

    # Build layer and MLP
    layer = BESSQPLayer(BESS, T=T_TRAIN, eps=EPS)
    mlp = PriceResidualMLP(input_dim=FEATURE_DIM)

    t0 = time.perf_counter()
    history = run_training(
        mlp=mlp,
        layer=layer,
        normalizer=norm,
        dataset=dataset,
        bess=BESS,
        train_days=train_days,
        val_days=val_days,
        checkpoint_dir=CHECKPOINT_DIR,
        T_train=T_TRAIN,
    )
    wall = time.perf_counter() - t0
    print(f"\n  Training wall-clock: {wall:.1f}s ({wall/60:.1f} min)")

    # Save history
    hist_path = CHECKPOINT_DIR / "dfl_training_history.json"
    hist_path.write_text(json.dumps(history, indent=2))
    print(f"  History saved to {hist_path}")
    return history


# ── Task 5 ────────────────────────────────────────────────────────────────────

def task_5_eval(dataset: ForecasterDataset) -> dict:
    print("\n=== Task 5: Eval on Apr 20–26 panel ===")

    ckpt_path = CHECKPOINT_DIR / "dfl_mlp_best.pt"
    if not ckpt_path.exists():
        print(f"  ERROR: checkpoint not found at {ckpt_path}")
        print("  Run --phase train first.")
        sys.exit(1)

    norm = FeatureNormalizer.load(NORMALIZER_PATH)
    mlp = PriceResidualMLP(input_dim=FEATURE_DIM)
    ckpt = torch.load(ckpt_path, map_location="cpu")
    mlp.load_state_dict(ckpt["model_state_dict"])
    mlp.eval()
    print(f"  Loaded checkpoint: epoch={ckpt['epoch']}, val_rev=${ckpt['val_rev']:,.1f}")

    t0 = time.perf_counter()
    result = eval_panel(mlp, norm, dataset, BESS, PANEL_START, PANEL_END)
    wall = time.perf_counter() - t0
    print(f"  Eval wall-clock: {wall:.1f}s")

    pf_total = _PF_ROW["total"]
    dfl_total = result.revenue_total

    print("\n=== Five-Method Comparison Table ===")
    print(f"{'Method':<42} {'Total':>10} {'Energy':>10} {'AS':>10} {'Term.Liq':>10} {'vs PF':>7}")
    print("-" * 95)

    rows = [
        ("PF LP (upper bound)",             _PF_ROW),
        ("Deterministic LP — DAM",          _DET_ROW),
        ("Deterministic LP — EV (scen mean)", _EV_ROW),
        ("Stochastic LP — scenario tree",   _STOCH_ROW),
    ]
    for name, r in rows:
        print(f"  {name:<40} ${r['total']:>9,} ${r['energy']:>9,} "
              f"${r['as_rev']:>9,} ${r['liq']:>9,}  "
              f"{r['total']/pf_total*100:>5.1f}%")

    dfl_row = dict(
        total=round(result.revenue_total),
        energy=round(result.revenue_energy),
        as_rev=round(result.revenue_as),
        liq=round(result.liquidation_revenue),
    )
    print(f"  {'DFL-MLP → Deterministic LP':<40} "
          f"${dfl_row['total']:>9,} "
          f"${dfl_row['energy']:>9,} "
          f"${dfl_row['as_rev']:>9,} "
          f"${dfl_row['liq']:>9,}  "
          f"{dfl_row['total']/pf_total*100:>5.1f}%")
    print("-" * 95)

    dfl_vs_ev    = dfl_row["total"] - _EV_ROW["total"]
    dfl_vs_dam   = dfl_row["total"] - _DET_ROW["total"]
    print(f"\n  DFL − EV (scenario mean): ${dfl_vs_ev:+,.0f}")
    print(f"  DFL − DAM deterministic:  ${dfl_vs_dam:+,.0f}")

    return {
        "dfl_total": dfl_row["total"],
        "dfl_energy": dfl_row["energy"],
        "dfl_as": dfl_row["as_rev"],
        "dfl_liq": dfl_row["liq"],
        "dfl_vs_pf_pct": dfl_row["total"] / pf_total * 100,
        "dfl_vs_ev_usd": dfl_vs_ev,
        "dfl_vs_dam_usd": dfl_vs_dam,
        "wall_s": wall,
        "checkpoint_epoch": int(ckpt["epoch"]),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="W3-D DFL backtest")
    parser.add_argument(
        "--phase",
        choices=["check", "train", "eval"],
        default="check",
        help=(
            "check: Task 0+1+3 (verify pipeline, report before training); "
            "train: Task 4 (full training); "
            "eval: Task 5 (five-method table)"
        ),
    )
    args = parser.parse_args()

    dataset = ForecasterDataset()

    if args.phase == "check":
        task_0_deps()
        task_1_verify_layer(dataset)
        task_3_single_day_overfit(dataset)

    elif args.phase == "train":
        history = task_4_full_training(dataset)
        print("\nTraining complete. Run --phase eval to generate the five-method table.")

    elif args.phase == "eval":
        eval_results = task_5_eval(dataset)
        # Save eval results for ADR / results file generation
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = AUDIT_DIR / "backtest_w3d_eval.json"
        out_path.write_text(json.dumps(eval_results, indent=2))
        print(f"\nEval results saved to {out_path}")
        print("\nStop: stage W3-D files for commit and report to chat for review.")


if __name__ == "__main__":
    main()
