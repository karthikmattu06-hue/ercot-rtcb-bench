"""DFL eval: generate MLP forecast → rolling pure LP on Apr 20–26 panel (W3-D).

At eval time the QP regulariser is NOT applied — the standard Gurobi rolling LP
(solve_deterministic_hour) is used so the eval method is directly comparable to
the W3-C deterministic LP runs. The DFL forecast replaces the DAM prices as the
LP input; the LP structure is unchanged.

Lookahead construction matches W3-C DAM-deterministic exactly:
  stage1: first T1=12 rows of the 24h forecast DataFrame
  stage2: remaining 276 rows
  terminal_lmp: mean(lmp) over the 24h window
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from datetime import date, timedelta
from pathlib import Path

from ercot_rtcb_bench.forecaster.data_loader import ForecasterDataset
from ercot_rtcb_bench.methods.battery import BESSParams
from ercot_rtcb_bench.methods.dfl.features import FeatureNormalizer, extract_features
from ercot_rtcb_bench.methods.dfl.forecaster import PriceResidualMLP
from ercot_rtcb_bench.methods.rolling_lp import (
    T1,
    RollingResult,
    run_rolling_lp,
    solve_deterministic_hour,
)

_PRICE_COLS = ["lmp", "mcpc_regup", "mcpc_regdn", "mcpc_rrs", "mcpc_ecrs", "mcpc_nspin"]


def _dfl_forecast_day(
    day: date,
    mlp: PriceResidualMLP,
    normalizer: FeatureNormalizer,
    dataset: ForecasterDataset,
) -> np.ndarray:
    """Return shape (6, 288) price forecast for *day* using the trained MLP.

    Final forecast = DAM prices (hourly broadcast) + MLP residual.
    AS prices are clipped ≥ 0; LMP can be negative.
    """
    features = extract_features(day, dataset)
    x = torch.from_numpy(normalizer.transform(features))
    with torch.no_grad():
        residual = mlp(x).numpy()  # (6, 288)
    dam = dataset.get_dam_array(day)  # (6, 288)
    forecast = np.nan_to_num(dam + residual, nan=0.0)
    forecast[1:] = np.maximum(forecast[1:], 0.0)  # AS ≥ 0
    return forecast.astype(np.float64)


def _build_price_df(
    prices_6x288: np.ndarray,
    hour_start: pd.Timestamp,
) -> pd.DataFrame:
    """Convert a (6, 288) forecast array to a 288-row DataFrame at 5-min resolution."""
    idx = pd.date_range(hour_start, periods=288, freq="5min")
    return pd.DataFrame(
        prices_6x288.T,
        index=idx,
        columns=_PRICE_COLS,
    )


def eval_panel(
    mlp: PriceResidualMLP,
    normalizer: FeatureNormalizer,
    dataset: ForecasterDataset,
    bess: BESSParams,
    panel_start: pd.Timestamp,
    panel_end: pd.Timestamp,
) -> RollingResult:
    """Run the DFL method on the eval panel using a pure rolling LP.

    For each eval hour the 24h lookahead is built from the DFL forecast:
      - Hours within a single day: full-day forecast sliced from h_within*12.
      - Hours near day boundaries: forecast stitched from current + next day.

    Args:
        mlp:          Trained PriceResidualMLP (eval mode).
        normalizer:   Fitted FeatureNormalizer.
        dataset:      ForecasterDataset for RT prices (settlement) and features.
        bess:         BESS physical parameters.
        panel_start:  First hour of eval window (UTC, inclusive).
        panel_end:    End of eval window (UTC, exclusive).

    Returns:
        RollingResult compatible with the W3-C table.
    """
    mlp.eval()

    # Pre-generate DFL forecasts for every operating day in the panel
    # plus one extra day for end-of-panel lookahead stitching.
    eval_days: list[date] = []
    d = panel_start.date()
    end_date = (panel_end + pd.Timedelta(hours=24)).date()
    while d <= end_date:
        eval_days.append(d)
        d += timedelta(days=1)

    print(f"  Generating DFL forecasts for {len(eval_days)} days...")
    forecast_cache: dict[date, np.ndarray] = {}
    for day in eval_days:
        try:
            forecast_cache[day] = _dfl_forecast_day(day, mlp, normalizer, dataset)
        except Exception as e:
            print(f"  Warning: forecast failed for {day}: {e}")
            # Fall back to DAM prices
            forecast_cache[day] = dataset.get_dam_array(day).astype(np.float64)

    # Load RT prices for settlement (all eval days)
    rt_start = panel_start - pd.Timedelta(hours=1)
    rt_end   = panel_end   + pd.Timedelta(hours=25)
    rt_rows: list[pd.DataFrame] = []
    d = panel_start.date()
    while d <= end_date:
        try:
            day_panel = dataset.get_day(d)
            rt_rows.append(day_panel[_PRICE_COLS].fillna(0.0))
        except Exception:
            pass
        d += timedelta(days=1)
    rt_prices = pd.concat(rt_rows).sort_index()

    def get_lookahead_dfl(h_utc: pd.Timestamp) -> dict:
        day = h_utc.date()
        h_within = h_utc.hour
        start_idx = h_within * 12  # 5-min index within the day

        fc_today = forecast_cache.get(day)
        if fc_today is None:
            raise KeyError(f"No DFL forecast for {day}")

        prices_tail = fc_today[:, start_idx:]          # (6, 288-start_idx)

        if start_idx > 0:
            next_day = day + timedelta(days=1)
            fc_next = forecast_cache.get(next_day, fc_today)
            prices_head = fc_next[:, :start_idx]       # (6, start_idx)
            prices_24h = np.concatenate([prices_tail, prices_head], axis=1)[:, :288]
        else:
            prices_24h = prices_tail[:, :288]

        # Pad if short (only happens when next-day forecast is missing)
        if prices_24h.shape[1] < 288:
            pad = np.repeat(prices_24h[:, -1:], 288 - prices_24h.shape[1], axis=1)
            prices_24h = np.concatenate([prices_24h, pad], axis=1)

        prices_df = _build_price_df(prices_24h, h_utc)
        stage1 = prices_df.iloc[:T1]
        stage2 = prices_df.iloc[T1:]
        return {
            "stage1": stage1,
            "stage2": stage2,
            "terminal_lmp": float(prices_df["lmp"].mean()),
        }

    def solve_hour(lookahead: dict, s_init: float):
        return solve_deterministic_hour(lookahead, bess, s_init)

    return run_rolling_lp(
        bess=bess,
        rt_prices=rt_prices,
        get_lookahead_fn=get_lookahead_dfl,
        solve_hour_fn=solve_hour,
        panel_start=panel_start,
        panel_end=panel_end,
    )
