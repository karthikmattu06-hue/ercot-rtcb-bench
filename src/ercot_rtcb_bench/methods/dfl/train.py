"""DFL training loop (W3-D).

Per-day online training: for each training day, build feature vector →
MLP forward → price forecast → diff-LP forward (1h horizon, T=12) →
first-hour decisions → settle at RT prices → loss = −revenue.

T_TRAIN=12 matches the committed horizon exactly: the diff-LP trains
on exactly the 12 5-min intervals it will settle, eliminating SCS
chain-constraint instability that occurs for T≥24.

SoC initialisation: s0=200 MWh (50% capacity) for all training days.
This is a PoC simplification — actual SoC is not tracked across days.

Training metric: first-hour settled revenue (midnight UTC = 7pm CDT).
Validation metric: same, on Apr 14–19 (held-out).
Early stopping: patience=3 epochs on val revenue.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from cvxpylayers.torch import CvxpyLayer

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.dfl.features import FeatureNormalizer, extract_features
from ercot_rtcb_bench.methods.dfl.forecaster import PriceResidualMLP

_T1 = 12    # committed intervals per hour (first hour)
_S0 = 200.0  # fixed initial SoC (MWh) for training

_RT_COLS = ["lmp", "mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]


def _preload(
    days: list[date],
    dataset: ForecasterDataset,
    normalizer: FeatureNormalizer,
) -> dict:
    """Pre-load and cache features, DAM arrays, and RT panels for a list of days."""
    cache: dict = {"features": {}, "dam": {}, "rt": {}}
    for d in days:
        raw = extract_features(d, dataset)
        cache["features"][d] = normalizer.transform(raw)
        cache["dam"][d] = dataset.get_dam_array(d).astype(np.float32)   # [6, 288]
        rt_raw = dataset.get_day(d)[_RT_COLS].to_numpy(dtype=np.float32)
        cache["rt"][d] = np.nan_to_num(rt_raw, nan=0.0)  # zero-fill missing RT prices
    return cache


def _step(
    day: date,
    cache: dict,
    mlp: PriceResidualMLP,
    layer: CvxpyLayer,
    bess: BESSParams,
    T_train: int,
    s0: float = _S0,
) -> torch.Tensor | None:
    """Single training step for one day. Returns loss scalar or None on solver failure."""
    dt = bess.dt_hours

    features_t = torch.from_numpy(cache["features"][day])      # (419,)
    dam_t      = torch.from_numpy(cache["dam"][day])            # (6, 288)
    rt_mat     = torch.from_numpy(cache["rt"][day])             # (288, 6)

    # Forecast = DAM + MLP residual; clip AS prices ≥ 0
    residual = mlp(features_t)                                  # (6, 288)
    forecast = dam_t + residual                                 # (6, 288)
    forecast_clipped = torch.cat([
        forecast[0:1],               # LMP: allow negative
        forecast[1:].clamp(min=0.0), # AS: non-negative
    ], dim=0)                                                   # (6, 288)

    # Extract training-horizon slice (first T_train 5-min intervals = first 6h)
    prices_tr = forecast_clipped[:, :T_train]                   # (6, T_train)

    s0_t    = torch.tensor(s0, dtype=torch.float32)
    term_t  = torch.tensor(0.0, dtype=torch.float32)           # no terminal value in training

    try:
        d_t, c_t, a_ru_t, a_rd_t, a_rrs_t, a_ecrs_t, a_ns_t, _s_t = layer(
            prices_tr[0], prices_tr[1], prices_tr[2],
            prices_tr[3], prices_tr[4], prices_tr[5],
            s0_t, term_t,
            solver_args={"max_iters": 10000, "eps": 1e-6},
        )
    except Exception:
        return None

    # Settle first T1=12 intervals at RT prices (constant — no grad needed)
    rt_first = rt_mat[:_T1]                  # (12, 6) — same order as _RT_COLS
    lmp_rt    = rt_first[:, 0]
    mcpc_ru   = rt_first[:, 1]
    mcpc_rd   = rt_first[:, 2]
    mcpc_rrs  = rt_first[:, 3]
    mcpc_ecrs = rt_first[:, 4]
    mcpc_ns   = rt_first[:, 5]

    rev = dt * (
        (lmp_rt * (d_t[:_T1] - c_t[:_T1])).sum()
        + (mcpc_ru   * a_ru_t[:_T1]).sum()
        + (mcpc_rd   * a_rd_t[:_T1]).sum()
        + (mcpc_rrs  * a_rrs_t[:_T1]).sum()
        + (mcpc_ecrs * a_ecrs_t[:_T1]).sum()
        + (mcpc_ns   * a_ns_t[:_T1]).sum()
    )
    if torch.isnan(rev):
        return None
    return -rev  # minimise negative revenue


def run_training(
    mlp: PriceResidualMLP,
    layer: CvxpyLayer,
    normalizer: FeatureNormalizer,
    dataset: ForecasterDataset,
    bess: BESSParams,
    train_days: list[date],
    val_days: list[date],
    checkpoint_dir: Path,
    T_train: int = 12,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    max_epochs: int = 20,
    patience: int = 3,
    seed: int = 42,
) -> dict:
    """Train the MLP end-to-end via decision regret.

    Args:
        mlp:            PriceResidualMLP to train (modified in-place).
        layer:          Pre-compiled BESSQPLayer (CvxpyLayer).
        normalizer:     Fitted FeatureNormalizer.
        dataset:        ForecasterDataset for data access.
        bess:           BESS physical parameters.
        train_days:     List of training dates.
        val_days:       List of validation dates (held-out for early stopping).
        checkpoint_dir: Where to save the best model checkpoint.
        T_train:        Training-horizon length in 5-min intervals (default 12 = 1h).
        lr:             Adam learning rate.
        weight_decay:   Adam L2 regularisation.
        max_epochs:     Maximum epochs before termination.
        patience:       Early-stop patience (epochs without val improvement).
        seed:           RNG seed for reproducible epoch shuffles.

    Returns:
        history dict with train_loss, val_revenue, best_epoch, best_val_rev.
    """
    torch.manual_seed(seed)
    random.seed(seed)

    print(f"Pre-loading {len(train_days)} train + {len(val_days)} val days...")
    train_cache = _preload(train_days, dataset, normalizer)
    val_cache   = _preload(val_days, dataset, normalizer)

    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = checkpoint_dir / "dfl_mlp_best.pt"

    optimizer = torch.optim.Adam(mlp.parameters(), lr=lr, weight_decay=weight_decay)

    history: dict = {
        "train_loss_per_epoch": [],
        "val_revenue_per_epoch": [],
        "best_epoch": 0,
        "best_val_rev": float("-inf"),
        "solver_failures": [],
    }
    best_val_rev = float("-inf")
    patience_count = 0

    for epoch in range(1, max_epochs + 1):
        mlp.train()
        shuffled = list(train_days)
        random.shuffle(shuffled)

        epoch_loss = 0.0
        failures = 0

        for day in shuffled:
            optimizer.zero_grad()
            loss = _step(day, train_cache, mlp, layer, bess, T_train)
            if loss is None:
                failures += 1
                continue
            loss.backward()
            # Skip step if gradients are NaN (prevents weight corruption)
            if any(
                p.grad is not None and torch.isnan(p.grad).any()
                for p in mlp.parameters()
            ):
                optimizer.zero_grad()
                failures += 1
                continue
            nn.utils.clip_grad_norm_(mlp.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_loss += float(loss.detach())

        # Validation
        mlp.eval()
        val_rev = 0.0
        with torch.no_grad():
            for day in val_days:
                step_loss = _step(day, val_cache, mlp, layer, bess, T_train)
                if step_loss is not None:
                    val_rev += -float(step_loss)  # loss is negative revenue

        history["train_loss_per_epoch"].append(epoch_loss)
        history["val_revenue_per_epoch"].append(val_rev)
        history["solver_failures"].append(failures)

        improved = val_rev > best_val_rev
        marker = " ✓" if improved else ""
        print(
            f"Epoch {epoch:2d}/{max_epochs}  "
            f"train_loss={epoch_loss:+,.1f}  "
            f"val_rev=${val_rev:,.1f}  "
            f"failures={failures}{marker}"
        )

        if improved:
            best_val_rev = val_rev
            best_epoch = epoch
            history["best_epoch"] = epoch
            history["best_val_rev"] = best_val_rev
            torch.save(
                {
                    "model_state_dict": mlp.state_dict(),
                    "epoch": epoch,
                    "val_rev": best_val_rev,
                },
                ckpt_path,
            )
            patience_count = 0
        else:
            patience_count += 1
            if patience_count >= patience:
                print(f"  Early stop: val_rev flat for {patience} epochs.")
                break

    print(f"\nBest checkpoint: epoch {history['best_epoch']}, val_rev=${history['best_val_rev']:,.1f}")
    print(f"Saved to: {ckpt_path}")
    return history
