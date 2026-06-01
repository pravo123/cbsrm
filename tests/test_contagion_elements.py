"""
Tests for cbsrm.networks.build_contagion_elements + the offline Streamlit
contagion-network viewer's pure data helper.

The Cytoscape block (2026-05-31) adds an interactive contagion
visualization. The load-bearing, testable artifact is the node/edge +
Cytoscape-elements JSON builder with per-node color states — these tests
pin its structure and color-state transitions (green/yellow/red), never a
rendered image. The Streamlit ``render()`` wrapper is exercised only via
its pure ``build_viewer_artifacts`` helper (no Streamlit import).

Run: pytest tests/test_contagion_elements.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from cbsrm.networks import (
    CONTAGION_ELEMENTS_VERSION,
    build_contagion_elements,
    debt_rank,
)


# ─── topology fixtures (mirror tests/test_debt_rank.py) ─────────────


def _chain_2node():
    L = np.array([[0.0, 0.0], [50.0, 0.0]])
    E = np.array([100.0, 100.0])
    return L, E


def _chain_3node():
    L = np.array([
        [0.0, 0.0, 0.0],
        [50.0, 0.0, 0.0],
        [0.0, 50.0, 0.0],
    ])
    E = np.array([100.0, 100.0, 100.0])
    return L, E


# ─── structure ─────────────────────────────────────────────────────


def test_elements_shape_and_keys():
    L, E = _chain_2node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    assert set(out.keys()) == {
        "version", "nodes", "edges", "cytoscape_elements", "summary",
    }
    assert out["version"] == CONTAGION_ELEMENTS_VERSION
    assert len(out["nodes"]) == 2
    for node in out["nodes"]:
        assert {"id", "label", "distress_initial", "distress_final",
                "state", "color"}.issubset(node.keys())


def test_output_is_json_serializable():
    L, E = _chain_3node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0, 0.0]))
    # Round-trips cleanly — no numpy scalars leak into the payload.
    text = json.dumps(out)
    again = json.loads(text)
    assert again["summary"]["n_nodes"] == 3


# ─── color-state transitions ───────────────────────────────────────


def test_defaulted_node_is_red():
    L, E = _chain_2node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    bank0 = next(n for n in out["nodes"] if n["id"] == "bank_0")
    # Seeded at distress 1.0 → defaulted → red.
    assert bank0["distress_final"] == pytest.approx(1.0)
    assert bank0["state"] == "defaulted"
    assert bank0["color"] == "red"


def test_partially_distressed_node_is_yellow():
    L, E = _chain_2node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    bank1 = next(n for n in out["nodes"] if n["id"] == "bank_1")
    # Receives 50/100 = 0.5 distress → distressed → yellow.
    assert bank1["distress_final"] == pytest.approx(0.5)
    assert bank1["state"] == "distressed"
    assert bank1["color"] == "yellow"


def test_untouched_node_is_green():
    # Disconnected node 1 never receives distress.
    L = np.array([[0.0, 0.0], [0.0, 0.0]])
    E = np.array([100.0, 100.0])
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    bank1 = next(n for n in out["nodes"] if n["id"] == "bank_1")
    assert bank1["distress_final"] == pytest.approx(0.0)
    assert bank1["state"] == "undistressed"
    assert bank1["color"] == "green"


# ─── edges ─────────────────────────────────────────────────────────


def test_edges_match_nonzero_exposures_with_direction():
    L, E = _chain_3node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0, 0.0]))
    # Two nonzero exposures: L[1,0] and L[2,1].
    edge_set = {(e["source"], e["target"], e["weight"]) for e in out["edges"]}
    # Loss flows from defaulter j → exposed bank i (i = row, j = col).
    assert ("bank_0", "bank_1", 50.0) in edge_set  # L[1,0]
    assert ("bank_1", "bank_2", 50.0) in edge_set  # L[2,1]
    assert len(out["edges"]) == 2


def test_self_loops_excluded():
    L = np.array([[5.0, 0.0], [10.0, 7.0]])  # diagonal entries present
    E = np.array([100.0, 100.0])
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    for e in out["edges"]:
        assert e["source"] != e["target"]


# ─── summary + labels + precomputed result ─────────────────────────


def test_summary_counts():
    L, E = _chain_2node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    s = out["summary"]
    assert s["n_nodes"] == 2
    assert s["n_defaulted"] == 1
    assert s["n_distressed"] == 1
    assert s["n_undistressed"] == 0
    assert s["n_edges"] == 1
    assert s["debt_rank"] > 0.0
    assert s["converged"] is True


def test_custom_labels_applied():
    L, E = _chain_2node()
    out = build_contagion_elements(
        L, E, np.array([1.0, 0.0]), labels=["SVB", "PEER"],
    )
    labels = {n["label"] for n in out["nodes"]}
    assert labels == {"SVB", "PEER"}


def test_wrong_label_count_raises():
    L, E = _chain_2node()
    with pytest.raises(ValueError):
        build_contagion_elements(L, E, np.array([1.0, 0.0]), labels=["only_one"])


def test_accepts_precomputed_result():
    L, E = _chain_2node()
    result = debt_rank(L, E, np.array([1.0, 0.0]))
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]), result=result)
    assert out["summary"]["debt_rank"] == pytest.approx(result["debt_rank"])


def test_cytoscape_elements_have_nodes_and_edges():
    L, E = _chain_2node()
    out = build_contagion_elements(L, E, np.array([1.0, 0.0]))
    els = out["cytoscape_elements"]
    node_els = [e for e in els if "source" not in e["data"]]
    edge_els = [e for e in els if "source" in e["data"]]
    assert len(node_els) == 2
    assert len(edge_els) == 1
    # Node elements carry the color state as a Cytoscape class.
    assert {e["classes"] for e in node_els} == {"defaulted", "distressed"}


# ─── Streamlit viewer pure helper (no Streamlit import) ────────────


_VIEWER_PATH = (
    Path(__file__).resolve().parents[1]
    / "dashboard"
    / "contagion_network_viewer.py"
)


def _load_viewer_module():
    assert _VIEWER_PATH.is_file(), f"viewer not found at {_VIEWER_PATH}"
    spec = importlib.util.spec_from_file_location(
        "_cbsrm_contagion_viewer_under_test", _VIEWER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_viewer_build_artifacts_without_streamlit():
    mod = _load_viewer_module()
    artifacts = mod.build_viewer_artifacts("2008Q4")
    assert artifacts["window_id"] == "2008Q4"
    assert "elements" in artifacts
    assert artifacts["summary"]["n_nodes"] == 4
    # The 2008Q4 seed node label is applied to bank_0.
    assert artifacts["seed_label"] == "EPICENTRE_BANK"
    # JSON artifact round-trips.
    json.loads(artifacts["elements_json"])


def test_viewer_unknown_window_raises():
    mod = _load_viewer_module()
    with pytest.raises(ValueError):
        mod.build_viewer_artifacts("BOGUS")
