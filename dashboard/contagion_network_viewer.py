"""Offline Streamlit viewer for the CBSRM contagion network.

A minimal, fully offline Streamlit page that lets a user pick one of the
canonical crisis windows (``2008Q4`` / ``2020Q1`` / ``2023Q1``), runs the
DebtRank cascade over that window's pinned interbank network, and renders
the resulting node/edge graph with per-node color states (green =
undistressed, yellow = distressed, red = defaulted).

Run::

    pip install cbsrm streamlit
    streamlit run dashboard/contagion_network_viewer.py

Design notes
------------
* All data logic lives in :func:`build_viewer_artifacts`, a pure function
  with no Streamlit dependency — testable without launching Streamlit.
* Streamlit is imported lazily inside :func:`render`, so importing this
  module (for tests / introspection) does not require Streamlit.
* No interactive-graph dependency is added (no cytoscape/plotly/networkx
  components): the page renders the deterministic node/edge tables plus the
  raw Cytoscape ``elements`` JSON (download-ready for any external
  Cytoscape.js front-end). Research only — NFA.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from cbsrm.diagnostics.crisis_dossiers import _FIXTURES, list_dossier_windows
from cbsrm.networks import build_contagion_elements


REPORT_CATALOG_VIEWER_PATH = "dashboard/report_catalog_viewer.py"


# ─── Pure helper (Streamlit-free) ────────────────────────────────────


def build_viewer_artifacts(window_id: str) -> dict[str, Any]:
    """Compose contagion-network elements + JSON artifacts for one window.

    Sources the interbank network (``L`` / ``E`` / ``h0`` / seed label)
    from the pinned crisis-window fixture and runs the DebtRank cascade
    through :func:`cbsrm.networks.build_contagion_elements`.

    Returns
    -------
    dict with keys:
        ``window_id``      — echoed input
        ``elements``       — full builder dict (nodes / edges /
                             cytoscape_elements / summary)
        ``elements_json``  — pretty JSON of ``elements`` (``indent=2``,
                             trailing newline) — download-ready
        ``summary``        — the cascade summary sub-dict
        ``seed_label``     — fixture's seed-node label
        ``json_filename``  — ``cbsrm_contagion_<window>.json``

    Raises
    ------
    ValueError
        If ``window_id`` is not a supported crisis window.
    """
    if window_id not in _FIXTURES:
        raise ValueError(
            f"unknown crisis window id {window_id!r}. "
            f"supported = {list_dossier_windows()}"
        )
    fx = _FIXTURES[window_id]
    L = np.array(fx.network_L, dtype=float)
    E = np.array(fx.network_E, dtype=float)
    h0 = np.array(fx.network_h0, dtype=float)
    n = L.shape[0]
    labels = [fx.network_seed_label if i == 0 else f"bank_{i}" for i in range(n)]

    elements = build_contagion_elements(L, E, h0, labels=labels)
    elements_json = json.dumps(elements, indent=2, ensure_ascii=False) + "\n"
    return {
        "window_id": window_id,
        "elements": elements,
        "elements_json": elements_json,
        "summary": elements["summary"],
        "seed_label": fx.network_seed_label,
        "json_filename": f"cbsrm_contagion_{window_id}.json",
    }


# ─── Streamlit UI (lazy streamlit import) ────────────────────────────


def render() -> None:
    """Render the Streamlit page. Imports Streamlit lazily so this module
    stays import-safe without Streamlit installed."""
    import streamlit as st

    st.set_page_config(page_title="Contagion Network", layout="wide")
    st.title("Contagion Network — DebtRank cascade")
    st.caption(
        "Deterministic, offline DebtRank contagion cascade over each "
        "crisis window's pinned interbank network. Nodes are colored by "
        "final distress: green = undistressed, yellow = distressed, "
        "red = defaulted. Research only — **not financial advice**."
    )

    windows = list(list_dossier_windows())
    with st.sidebar:
        st.markdown("### Window")
        window_id = st.selectbox("Select crisis window", windows)

    artifacts = build_viewer_artifacts(window_id)
    summary = artifacts["summary"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("DebtRank", f"{summary['debt_rank']:.4f}")
    with c2:
        st.metric("Defaulted", summary["n_defaulted"])
    with c3:
        st.metric("Distressed", summary["n_distressed"])
    with c4:
        st.metric("Undistressed", summary["n_undistressed"])

    st.markdown("### Nodes")
    st.dataframe(
        [
            {
                "id": n["id"],
                "label": n["label"],
                "state": n["state"],
                "color": n["color"],
                "distress_initial": n["distress_initial"],
                "distress_final": n["distress_final"],
            }
            for n in artifacts["elements"]["nodes"]
        ],
        use_container_width=True,
    )

    st.markdown("### Edges (loss flow: defaulter → exposed bank)")
    st.dataframe(artifacts["elements"]["edges"], use_container_width=True)

    st.markdown("### Cytoscape elements (JSON)")
    st.json(artifacts["elements"]["cytoscape_elements"])
    st.download_button(
        label="Download elements (.json)",
        data=artifacts["elements_json"].encode("utf-8"),
        file_name=artifacts["json_filename"],
        mime="application/json",
    )

    st.caption(
        "Catalog landing page: "
        f"`{REPORT_CATALOG_VIEWER_PATH}` — run "
        f"`streamlit run {REPORT_CATALOG_VIEWER_PATH}`."
    )


if __name__ == "__main__":  # pragma: no cover - exercised by `streamlit run`
    render()
