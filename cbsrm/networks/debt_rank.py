"""
DebtRank — pure-numpy systemic-risk centrality on a financial network.

Reference
---------

Battiston, S., Puliga, M., Kaushik, R., Tasca, P., & Caldarelli, G. (2012).
DebtRank: Too Central to Fail? Financial Networks, the FED and Systemic Risk.
*Scientific Reports*, 2, 541.

Methodology
-----------

DebtRank quantifies the systemic impact of a shock to one or more nodes in a
financial network. Unlike eigenvector centrality, which double-counts cyclic
influence, DebtRank uses a state machine (Undistressed / Distressed /
Inactive) that bounds each node's contribution to a single propagation step.

Given:

* ``L`` — interbank exposure matrix, shape (N, N). ``L[i, j]`` is the
  exposure of bank ``i`` TO bank ``j``: the loss bank ``i`` would book if
  bank ``j`` defaults.
* ``E`` — equity / capital cushion vector, shape (N,).
* ``h0`` — initial distress vector, shape (N,), values in ``[0, 1]``.

The leverage / vulnerability matrix is::

    W[i, j] = min(L[i, j] / E[i], 1.0)    if E[i] > 0
            = 0                            otherwise

with the diagonal forced to 0 (self-loops do not propagate).

State machine:

* ``U`` (undistressed) — eligible to receive impact this step.
* ``D`` (distressed)   — propagates impact to its lenders this step.
* ``I`` (inactive)     — already propagated; cannot propagate again.

At each iteration, for every ``U`` node ``j``::

    h_j(t+1) = min(1, h_j(t) + sum_{i in D} W[j, i] * h_i(t))

Then all ``D`` nodes flip to ``I``. Any ``U`` node whose distress increased
above 0 flips to ``D``. The loop terminates when no ``D`` nodes remain, when
the change falls below ``tol``, or when ``max_iter`` is reached.

The scalar DebtRank is the importance-weighted sum of the distress increment::

    DR = sum_i v_i * (h_final[i] - h_initial[i])

where ``v_i`` is the economic-importance weight of node ``i`` (default
uniform ``1 / N``). Caller may supply custom ``v``; if it does not sum to 1
it will be renormalized with a warning.

Validation invariants
~~~~~~~~~~~~~~~~~~~~~

The unit-test suite asserts:

* Disconnected graph (``L`` all zeros) → no cascade; DR equals the importance-
  weighted initial distress contribution.
* Self-loops do not contribute (``L[i, i]`` set non-zero has no effect).
* Scaling ``L`` and ``E`` by the same positive factor leaves ``W`` and thus
  DR unchanged.
* Shocking a high-``v`` node yields a strictly larger DR than shocking a
  low-``v`` node with the same downstream topology.
* Pathological deep cascades terminate at ``max_iter`` with
  ``converged=False``.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np


def _validate_inputs(
    L: np.ndarray,
    E: np.ndarray,
    h0: np.ndarray,
    v: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate and canonicalize DebtRank inputs.

    Returns ``(L_arr, E_arr, h0_arr, v_arr)`` as float64 arrays.
    Raises ``ValueError`` on shape mismatch, negative exposures, or h0 out
    of bounds. Negative equities are clipped to 0 with a warning; non-
    normalized ``v`` is renormalized with a warning.
    """
    L_arr = np.asarray(L, dtype=float)
    E_arr = np.asarray(E, dtype=float)
    h0_arr = np.asarray(h0, dtype=float)

    if L_arr.ndim != 2:
        raise ValueError(
            f"L must be 2-D, got ndim={L_arr.ndim} shape={L_arr.shape}"
        )
    if L_arr.shape[0] != L_arr.shape[1]:
        raise ValueError(
            f"L must be square (N, N); got shape={L_arr.shape}"
        )
    N = L_arr.shape[0]

    if E_arr.ndim != 1 or E_arr.shape[0] != N:
        raise ValueError(
            f"E must be shape (N,) with N={N}; got shape={E_arr.shape}"
        )
    if h0_arr.ndim != 1 or h0_arr.shape[0] != N:
        raise ValueError(
            f"h0 must be shape (N,) with N={N}; got shape={h0_arr.shape}"
        )

    if not np.all(np.isfinite(L_arr)):
        raise ValueError("L contains non-finite values (NaN/Inf)")
    if not np.all(np.isfinite(E_arr)):
        raise ValueError("E contains non-finite values (NaN/Inf)")
    if not np.all(np.isfinite(h0_arr)):
        raise ValueError("h0 contains non-finite values (NaN/Inf)")

    if np.any(L_arr < 0):
        raise ValueError("L must be non-negative (exposures cannot be < 0)")

    if np.any((h0_arr < 0.0) | (h0_arr > 1.0)):
        raise ValueError("h0 entries must lie in [0, 1]")

    if np.any(E_arr < 0):
        warnings.warn(
            "Negative equities in E will be clipped to 0 "
            "(DebtRank assumes non-negative capital cushions).",
            RuntimeWarning,
            stacklevel=3,
        )
        E_arr = np.clip(E_arr, 0.0, None)

    if v is None:
        v_arr = np.full(N, 1.0 / N, dtype=float)
    else:
        v_arr = np.asarray(v, dtype=float)
        if v_arr.ndim != 1 or v_arr.shape[0] != N:
            raise ValueError(
                f"v must be shape (N,) with N={N}; got shape={v_arr.shape}"
            )
        if not np.all(np.isfinite(v_arr)):
            raise ValueError("v contains non-finite values (NaN/Inf)")
        if np.any(v_arr < 0):
            raise ValueError("v must be non-negative")
        v_sum = v_arr.sum()
        if v_sum <= 0:
            raise ValueError("v must have a strictly positive sum")
        if not np.isclose(v_sum, 1.0, atol=1e-9):
            warnings.warn(
                f"Economic-weight vector v sums to {v_sum:.6g}, not 1.0; "
                "renormalizing.",
                RuntimeWarning,
                stacklevel=3,
            )
            v_arr = v_arr / v_sum

    return L_arr, E_arr, h0_arr, v_arr


def _leverage_matrix(L: np.ndarray, E: np.ndarray) -> np.ndarray:
    """Construct W[i, j] = min(L[i, j] / E[i], 1) with W[i, i] = 0."""
    N = L.shape[0]
    W = np.zeros_like(L, dtype=float)
    safe = E > 0
    if np.any(safe):
        # Row-wise division by E[i] for rows where E[i] > 0
        W[safe, :] = L[safe, :] / E[safe, np.newaxis]
    W = np.minimum(W, 1.0)
    # Kill self-loops: a bank's exposure to itself never propagates.
    np.fill_diagonal(W, 0.0)
    return W


# Node state codes (kept as integer enum for fast vectorized comparisons).
_STATE_U = 0  # undistressed, can be impacted
_STATE_D = 1  # distressed, propagates this step
_STATE_I = 2  # inactive, already propagated


def debt_rank(
    L: np.ndarray,
    E: np.ndarray,
    h0: np.ndarray,
    v: np.ndarray | None = None,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> dict[str, Any]:
    """Compute DebtRank centrality for a financial network.

    Parameters
    ----------
    L : (N, N) array
        Interbank exposure matrix. ``L[i, j]`` is what bank ``i`` would lose
        if bank ``j`` defaulted (i.e. i's exposure TO j). Must be non-negative.
        The diagonal is ignored.
    E : (N,) array
        Equity / capital cushion per bank. Negative entries are clipped to 0
        with a ``RuntimeWarning``. Rows where ``E[i] == 0`` get a zero leverage
        row (their losses cannot be absorbed; cascade-wise they are passive).
    h0 : (N,) array
        Initial distress per bank, in ``[0, 1]``. Non-zero entries seed the
        cascade.
    v : (N,) array, optional
        Economic-importance weight per bank. Defaults to uniform ``1/N``.
        Will be renormalized to sum to 1 if needed.
    max_iter : int, default 100
        Maximum propagation steps.
    tol : float, default 1e-9
        Distress-change threshold for early termination.

    Returns
    -------
    dict
        ``distress_final`` : (N,) np.ndarray — final distress vector
        ``distress_initial`` : (N,) np.ndarray — copy of h0 (post-validation)
        ``debt_rank`` : float — Σ v_i (h_final[i] - h_initial[i])
        ``node_contributions`` : (N,) np.ndarray — v_i * (h_final[i] - h_initial[i])
        ``iterations`` : int — propagation steps actually taken
        ``converged`` : bool — True if loop ended before ``max_iter``
        ``leverage_matrix`` : (N, N) np.ndarray — W = min(L/E, 1)
        ``economic_weights`` : (N,) np.ndarray — normalized v

    Notes
    -----
    DebtRank's state machine bounds each node's downstream impact to a single
    propagation step, which avoids the cyclic double-counting that inflates
    eigenvector-centrality measures. See Battiston et al. (2012), Fig. 1.
    """
    L_arr, E_arr, h0_arr, v_arr = _validate_inputs(L, E, h0, v)
    N = L_arr.shape[0]

    W = _leverage_matrix(L_arr, E_arr)

    h = h0_arr.copy()
    h_initial = h0_arr.copy()

    # State init: nodes with positive initial distress are D, rest are U.
    state = np.where(h > 0.0, _STATE_D, _STATE_U).astype(np.int8)

    iterations = 0
    converged = False
    for step in range(1, max_iter + 1):
        iterations = step
        distressed_mask = state == _STATE_D
        if not np.any(distressed_mask):
            converged = True
            break

        undistressed_mask = state == _STATE_U
        # Impact each U-node j receives from currently-D nodes i:
        #   sum_i W[j, i] * h[i]  for i in D
        impact = W[:, distressed_mask] @ h[distressed_mask]
        # Only U-nodes update; clip to 1.
        new_h = h.copy()
        if np.any(undistressed_mask):
            new_h[undistressed_mask] = np.minimum(
                1.0, h[undistressed_mask] + impact[undistressed_mask]
            )

        delta = float(np.abs(new_h - h).sum())
        h = new_h

        # Nodes that have just propagated become inactive.
        new_state = state.copy()
        new_state[distressed_mask] = _STATE_I
        # Newly-distressed U-nodes (positive impact this step) become D.
        became_distressed = undistressed_mask & (impact > 0.0)
        new_state[became_distressed] = _STATE_D
        state = new_state

        if delta < tol and not np.any(state == _STATE_D):
            converged = True
            break

    node_contrib = v_arr * (h - h_initial)
    dr = float(node_contrib.sum())

    return {
        "distress_final": h,
        "distress_initial": h_initial,
        "debt_rank": dr,
        "node_contributions": node_contrib,
        "iterations": iterations,
        "converged": converged,
        "leverage_matrix": W,
        "economic_weights": v_arr,
    }
