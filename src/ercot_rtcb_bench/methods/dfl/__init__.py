"""Decision-Focused Learning (DFL) BESS bidding method — W3-D PoC."""

from ercot_rtcb_bench.methods.dfl.diff_lp import T_TRAIN, EPS, BESSQPLayer
from ercot_rtcb_bench.methods.dfl.features import FEATURE_DIM, FeatureNormalizer, extract_features
from ercot_rtcb_bench.methods.dfl.forecaster import PriceResidualMLP

__all__ = [
    "T_TRAIN",
    "EPS",
    "FEATURE_DIM",
    "BESSQPLayer",
    "FeatureNormalizer",
    "extract_features",
    "PriceResidualMLP",
]
