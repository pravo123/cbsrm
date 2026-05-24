"""Offline Streamlit viewer for the CBSRM v0.9 macro-composite report.

A minimal, fully offline Streamlit page that lets a user pick one of the
canonical macro-composite windows (``2008Q4`` / ``2020Q1`` / ``2023Q1``),
renders the deterministic Markdown report, and offers Markdown / JSON
downloads of the same report payload the in-process builder exposes.

Run::

    pip install cbsrm streamlit
    streamlit run dashboard/macro_composite_viewer.py

Design notes
------------
* All data logic lives in :func:`build_viewer_artifacts`, a pure function
  with no Streamlit dependency. This keeps the helper testable without
  launching Streamlit and without requiring Streamlit to be installed in
  the test environment.
* Streamlit is imported lazily inside :func:`render`, so importing this
  module — for tests or for offline introspection — does not require
  Streamlit.
* No FRED key, no network calls, no API server dependency, no auth, no
  billing, no PDF generation, no persistence, no manifest / audit-DB /
  report-store sidebar. Research only — NFA.
"""
from __future__ import annotations

import json
from typing import Any

from cbsrm.reporting import (
    build_macro_composite_report,
    list_macro_composite_windows,
    render_macro_composite_markdown,
)


# Path string used to point users at the catalog landing page. Kept at
# module scope so tests can pin it without re-deriving the constant.
REPORT_CATALOG_VIEWER_PATH = "dashboard/report_catalog_viewer.py"


# ─── Pure helper (Streamlit-free) ────────────────────────────────────


def build_viewer_artifacts(window_id: str) -> dict[str, Any]:
    """Compose report + Markdown + canonical JSON artifacts for one window.

    Parameters
    ----------
    window_id
        One of the canonical window IDs returned by
        :func:`cbsrm.reporting.list_macro_composite_windows`.

    Returns
    -------
    dict with keys:
        ``window_id``         — the input, echoed for caller convenience
        ``report``            — raw report dict from
                                :func:`cbsrm.reporting.build_macro_composite_report`
        ``markdown``          — deterministic Markdown report (str)
        ``json_text``         — canonical JSON serialisation of ``report``
                                (``indent=2``, ``ensure_ascii=False``, with
                                a single trailing newline). The
                                ``ensure_ascii=False`` flag matters: the
                                report title contains an em-dash (``—``)
                                which must round-trip intact.
        ``markdown_filename`` — ``cbsrm_macro_composite_<window>.md``
        ``json_filename``     — ``cbsrm_macro_composite_<window>.json``

    Raises
    ------
    ValueError
        If ``window_id`` is not in the supported set (propagated
        verbatim from :func:`build_macro_composite_report`).

    Notes
    -----
    Pure, deterministic, Streamlit-free. Same input → byte-identical
    ``markdown`` and ``json_text``.
    """
    report = build_macro_composite_report(window_id)
    markdown_text = render_macro_composite_markdown(report)
    json_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    return {
        "window_id": window_id,
        "report": report,
        "markdown": markdown_text,
        "json_text": json_text,
        "markdown_filename": f"cbsrm_macro_composite_{window_id}.md",
        "json_filename": f"cbsrm_macro_composite_{window_id}.json",
    }


# ─── Streamlit UI (lazy streamlit import) ────────────────────────────


def render() -> None:
    """Render the Streamlit page. Imports Streamlit lazily so this
    module stays import-safe in environments without Streamlit
    installed."""
    import streamlit as st

    st.set_page_config(
        page_title="Macro Composite Snapshot",
        layout="wide",
    )
    st.title("Macro Composite Snapshot")
    st.caption(
        "Deterministic, offline, fixture-backed v0.9 macro-composite "
        "report rendered through the canonical Markdown renderer. "
        "No live data, no network calls, no API server required. "
        "Research only — **not financial advice**."
    )

    windows = list(list_macro_composite_windows())
    with st.sidebar:
        st.markdown("### Window")
        window_id = st.selectbox(
            "Select macro-composite window", windows,
        )

    artifacts = build_viewer_artifacts(window_id)
    report = artifacts["report"]
    phase = report["phase_classification"]
    phase_label = phase.get("phase", "indeterminate")
    score = phase.get("score", 0.0)
    risk_posture = phase.get("risk_posture", "unspecified")
    drivers = phase.get("dominant_drivers", []) or []

    col_window, col_phase, col_score, col_risk = st.columns(4)
    with col_window:
        st.metric("Window", artifacts["window_id"])
    with col_phase:
        st.metric("Phase", str(phase_label))
    with col_score:
        st.metric("Score", f"{float(score):.3f}")
    with col_risk:
        st.metric("Risk posture", str(risk_posture))

    st.markdown("**Dominant drivers**")
    if drivers:
        for d in drivers:
            st.markdown(f"- `{d}`")
    else:
        st.markdown("_(none)_")

    col_md, col_json = st.columns(2)
    with col_md:
        st.download_button(
            label="Download Markdown (.md)",
            data=artifacts["markdown"].encode("utf-8"),
            file_name=artifacts["markdown_filename"],
            mime="text/markdown",
        )
    with col_json:
        st.download_button(
            label="Download JSON (.json)",
            data=artifacts["json_text"].encode("utf-8"),
            file_name=artifacts["json_filename"],
            mime="application/json",
        )

    st.markdown("---")
    st.markdown(artifacts["markdown"])

    st.caption(
        "Catalog landing page: "
        f"`{REPORT_CATALOG_VIEWER_PATH}` — run "
        f"`streamlit run {REPORT_CATALOG_VIEWER_PATH}`."
    )


if __name__ == "__main__":  # pragma: no cover - exercised by `streamlit run`
    render()
