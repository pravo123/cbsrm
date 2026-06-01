"""
Contagion-network visualization elements.
=========================================
Turns a DebtRank cascade into a unit-testable node/edge graph with
per-node color states, plus a Cytoscape.js-ready ``elements`` list for an
interactive front-end.

The DebtRank engine (:func:`cbsrm.networks.debt_rank`) already returns the
per-node ``distress_final`` / ``distress_initial`` vectors, so this module
is a pure, deterministic transform — no new methodology, no rendering, no
network, no pixels. Tests assert the JSON structure and color-state
transitions, never a rendered image.

Color states (per node final distress ``h``):

* ``h <= EPS``            → ``undistressed``  → **green**
* ``EPS < h < 1 - EPS``   → ``distressed``    → **yellow**
* ``h >= 1 - EPS``        → ``defaulted``     → **red**

Edge direction follows the loss flow: an exposure ``L[i, j] > 0`` (bank
``i`` loses if bank ``j`` defaults) becomes an edge ``source=bank_j →
target=bank_i`` weighted by the exposure.

Public surface
~~~~~~~~~~~~~~

* :func:`build_contagion_elements` — ``(L, E, h0, ...) -> dict`` with
  ``nodes``, ``edges``, ``cytoscape_elements`` and a ``summary``.
* :data:`CONTAGION_ELEMENTS_VERSION`.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from cbsrm.networks.debt_rank import debt_rank


CONTAGION_ELEMENTS_VERSION = "1.0.0"

# Distress epsilon — distinguishes numerically-zero distress (green) and
# fully-defaulted (red) from the partially-distressed middle band (yellow).
_EPS = 1e-9

_STATE_COLORS = {
    "undistressed": "green",
    "distressed": "yellow",
    "defaulted": "red",
}


def _classify_state(distress: float) -> str:
    if distress <= _EPS:
        return "undistressed"
    if distress >= 1.0 - _EPS:
        return "defaulted"
    return "distressed"


def build_contagion_elements(
    L: np.ndarray,
    E: np.ndarray,
    h0: np.ndarray,
    *,
    labels: list[str] | None = None,
    v: np.ndarray | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build node/edge + Cytoscape elements from a DebtRank cascade.

    Parameters
    ----------
    L, E, h0 :
        DebtRank inputs (exposure matrix, equity vector, initial distress).
    labels :
        Optional human labels per node (defaults to ``bank_0 ... bank_{N-1}``).
    v :
        Optional economic-importance weights forwarded to :func:`debt_rank`.
    result :
        Optional precomputed :func:`debt_rank` result; when ``None`` the
        cascade is run here. Lets callers avoid a double computation.

    Returns
    -------
    dict
        ``{"nodes": [...], "edges": [...], "cytoscape_elements": [...],
           "summary": {...}, "version": CONTAGION_ELEMENTS_VERSION}`` —
        fully JSON-serializable (no numpy scalars).
    """
    L_arr = np.asarray(L, dtype=float)
    n = L_arr.shape[0]

    if result is None:
        result = debt_rank(L_arr, E, h0, v=v)

    distress_final = np.asarray(result["distress_final"], dtype=float)
    distress_initial = np.asarray(result["distress_initial"], dtype=float)

    if labels is None:
        labels = [f"bank_{i}" for i in range(n)]
    elif len(labels) != n:
        raise ValueError(
            f"labels length {len(labels)} != network size {n}"
        )

    node_ids = [f"bank_{i}" for i in range(n)]

    nodes: list[dict[str, Any]] = []
    n_distressed = 0
    n_defaulted = 0
    for i in range(n):
        h_final = float(distress_final[i])
        state = _classify_state(h_final)
        if state == "distressed":
            n_distressed += 1
        elif state == "defaulted":
            n_defaulted += 1
        nodes.append({
            "id": node_ids[i],
            "label": str(labels[i]),
            "distress_initial": float(distress_initial[i]),
            "distress_final": h_final,
            "state": state,
            "color": _STATE_COLORS[state],
        })

    edges: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            w = float(L_arr[i, j])
            if w > 0.0:
                # Loss flows FROM the (potential) defaulter j TO the
                # exposed bank i.
                edges.append({
                    "source": node_ids[j],
                    "target": node_ids[i],
                    "weight": w,
                })

    cytoscape_elements: list[dict[str, Any]] = [
        {
            "data": {
                "id": node["id"],
                "label": node["label"],
                "distress_final": node["distress_final"],
                "color": node["color"],
            },
            "classes": node["state"],
        }
        for node in nodes
    ]
    cytoscape_elements += [
        {
            "data": {
                "id": f"{edge['source']}->{edge['target']}",
                "source": edge["source"],
                "target": edge["target"],
                "weight": edge["weight"],
            }
        }
        for edge in edges
    ]

    summary = {
        "debt_rank": float(result["debt_rank"]),
        "n_nodes": int(n),
        "n_edges": int(len(edges)),
        "n_distressed": int(n_distressed),
        "n_defaulted": int(n_defaulted),
        "n_undistressed": int(n - n_distressed - n_defaulted),
        "iterations": int(result["iterations"]),
        "converged": bool(result["converged"]),
    }

    return {
        "version": CONTAGION_ELEMENTS_VERSION,
        "nodes": nodes,
        "edges": edges,
        "cytoscape_elements": cytoscape_elements,
        "summary": summary,
    }


__all__ = [
    "build_contagion_elements",
    "CONTAGION_ELEMENTS_VERSION",
]
