"""Task 3 — K-medoids scenario reduction.

Reduces N raw scenarios [N × 6 × 288] to K representative scenarios [K × 6 × 288].

Design decisions (ADR 0007):
  - K-medoids (not K-means): medoids are actual scenarios, preserving whole-day-block
    cross-series and temporal coherence that K-means centroids would destroy.
  - Distance: Euclidean on flattened [6 × 288] vectors with per-series z-normalization
    so $/MWh-scale LMP does not dominate $/MW-scale AS products.
  - Probabilities: each medoid's weight = fraction of raw scenarios in its cluster.
  - If N ≤ K: skip reduction, return all scenarios with uniform weights.

Implementation: PAM (Partitioning Around Medoids) — exact, O(K × iter × N²).
Efficient enough for N ≤ 40, K = 15.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_K = 15
MAX_PAM_ITER = 100


def _normalize_features(scenarios: np.ndarray) -> np.ndarray:
    """Z-normalize each series across all N scenarios.

    Parameters
    ----------
    scenarios : np.ndarray, shape [N, 6, 288]

    Returns
    -------
    np.ndarray, shape [N, 6 * 288]
        Flattened, per-series z-normalized feature matrix.
    """
    n = scenarios.shape[0]
    flat = scenarios.reshape(n, -1)          # [N, 6*288]

    n_series, n_steps = scenarios.shape[1], scenarios.shape[2]
    normed = flat.copy()

    for s in range(n_series):
        cols = slice(s * n_steps, (s + 1) * n_steps)
        block = flat[:, cols]
        mu = block.mean()
        sigma = block.std()
        if sigma > 1e-8:
            normed[:, cols] = (block - mu) / sigma
        else:
            normed[:, cols] = 0.0

    return normed


def _pairwise_dist(features: np.ndarray) -> np.ndarray:
    """Compute N×N pairwise Euclidean distance matrix."""
    n = features.shape[0]
    # Use broadcasting for clarity; for N≤40 this is trivially fast
    diff = features[:, None, :] - features[None, :, :]  # [N, N, D]
    return np.sqrt((diff ** 2).sum(axis=-1))             # [N, N]


def kmedoids(
    scenarios: np.ndarray,
    k: int = DEFAULT_K,
    max_iter: int = MAX_PAM_ITER,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PAM k-medoids on [N × 6 × 288] scenarios.

    Parameters
    ----------
    scenarios : np.ndarray, shape [N, 6, 288]
    k : int
        Target number of representative scenarios.
    max_iter : int
        Maximum PAM swap iterations.
    random_seed : int
        Seed for initial medoid selection.

    Returns
    -------
    medoid_scenarios : np.ndarray, shape [K, 6, 288]
        The K representative scenarios (actual scenarios, not centroids).
    probabilities : np.ndarray, shape [K]
        Cluster weight = fraction of raw scenarios assigned to each medoid.
        Sums to 1.0.
    assignments : np.ndarray, shape [N]
        Cluster index (0..K-1) for each raw scenario.
    """
    n = scenarios.shape[0]

    if n <= k:
        logger.info("N=%d ≤ K=%d: returning all scenarios with uniform weights", n, k)
        probs = np.full(n, 1.0 / n)
        return scenarios.copy(), probs, np.arange(n)

    features = _normalize_features(scenarios)      # [N, D]
    dist_mat = _pairwise_dist(features)             # [N, N]

    # Initialize medoids with k-medoids++ (greedy, distance-weighted)
    rng = np.random.default_rng(random_seed)
    medoid_idx = _init_kmedoids_plus(dist_mat, k, rng)

    for iteration in range(max_iter):
        # Assignment: each point to nearest medoid
        assignments = dist_mat[:, medoid_idx].argmin(axis=1)  # [N]

        # Swap phase: for each medoid, try swapping with each non-medoid
        changed = False
        medoid_set = set(medoid_idx.tolist())

        for mi, m in enumerate(medoid_idx):
            cluster_mask = assignments == mi
            cluster_pts = np.where(cluster_mask)[0]
            if len(cluster_pts) == 0:
                continue

            # Current within-cluster cost
            current_cost = dist_mat[cluster_pts, m].sum()

            best_swap = m
            best_cost = current_cost

            for candidate in cluster_pts:
                if candidate == m:
                    continue
                cost = dist_mat[cluster_pts, candidate].sum()
                if cost < best_cost:
                    best_cost = cost
                    best_swap = candidate

            if best_swap != m:
                medoid_idx[mi] = best_swap
                changed = True

        if not changed:
            logger.debug("k-medoids converged at iteration %d", iteration + 1)
            break

    # Final assignment
    assignments = dist_mat[:, medoid_idx].argmin(axis=1)  # [N]

    # Compute probabilities as cluster sizes / N
    probs = np.array(
        [float((assignments == ki).sum()) / n for ki in range(k)],
        dtype=np.float64,
    )

    # Handle degenerate empty clusters (rare; give them zero weight)
    probs /= probs.sum()

    medoid_scenarios = scenarios[medoid_idx].copy()  # [K, 6, 288]

    logger.debug(
        "k-medoids: %d → %d scenarios, cluster sizes %s",
        n, k, [(assignments == ki).sum() for ki in range(k)],
    )
    return medoid_scenarios, probs, assignments


def _init_kmedoids_plus(
    dist_mat: np.ndarray,
    k: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """k-medoids++ initialization: pick first medoid uniformly, rest by distance²."""
    n = dist_mat.shape[0]
    medoids = [int(rng.integers(0, n))]

    for _ in range(1, k):
        # Distance from each point to its nearest already-chosen medoid
        min_dists = dist_mat[:, medoids].min(axis=1)  # [N]
        weights = min_dists ** 2
        total = weights.sum()
        if total < 1e-12:
            probs = np.full(n, 1.0 / n)
        else:
            probs = weights / total
        medoids.append(int(rng.choice(n, p=probs)))

    return np.array(medoids, dtype=int)


def reduce_scenarios(
    raw_scenarios: np.ndarray,
    k: int = DEFAULT_K,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """High-level wrapper: reduce [N × 6 × 288] → [K × 6 × 288] + probabilities.

    Parameters
    ----------
    raw_scenarios : np.ndarray, shape [N, 6, 288]
    k : int
        Target number of representative scenarios.
    random_seed : int

    Returns
    -------
    scenarios : np.ndarray, shape [min(N,K), 6, 288]
    probabilities : np.ndarray, shape [min(N,K)]
    """
    if raw_scenarios.shape[0] == 0:
        raise ValueError("No raw scenarios to reduce")

    medoid_scenarios, probs, _ = kmedoids(raw_scenarios, k=k, random_seed=random_seed)
    return medoid_scenarios, probs
