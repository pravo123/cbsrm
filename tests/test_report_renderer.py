"""
Tests for cbsrm.reporting.report_renderer — deterministic Markdown + JSON
renderer for crisis-window dossiers.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from cbsrm.diagnostics import build_crisis_dossier
from cbsrm.diagnostics.crisis_dossiers import CRISIS_DOSSIER_WINDOWS
from cbsrm.reporting import (
    NFA_DISCLAIMER,
    REPORT_RENDERER_VERSION,
    build_report_payload,
    render_dossier_markdown,
)


# ─── Markdown rendering — all 3 windows ────────────────────────────


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_markdown_renders_for_every_window(window_id):
    dossier = build_crisis_dossier(window_id)
    md = render_dossier_markdown(dossier)
    assert isinstance(md, str)
    assert len(md) > 500


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_markdown_required_sections_present(window_id):
    dossier = build_crisis_dossier(window_id)
    md = render_dossier_markdown(dossier)
    # title line
    assert md.startswith(f"# {dossier['title']}")
    # standard section headings
    for heading in (
        "## Shock summary",
        "## Phase classification",
        "## Macro event scores",
        "## Replay summary",
        "## Network stress summary",
        "## Research notes",
        "## Spec",
    ):
        assert heading in md, f"{window_id}: missing heading {heading!r}"


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_markdown_includes_window_id_period_and_phase(window_id):
    dossier = build_crisis_dossier(window_id)
    md = render_dossier_markdown(dossier)
    assert f"`{window_id}`" in md
    assert dossier["period"]["start"] in md
    assert dossier["period"]["end"] in md
    assert f"`{dossier['phase_label']}`" in md
    assert f"`{dossier['risk_posture']}`" in md


def test_markdown_includes_macro_event_table_for_2008q4():
    md = render_dossier_markdown(build_crisis_dossier("2008Q4"))
    # table header + at least one NFP row
    assert "| event | release_date | actual | consensus | surprise |" in md
    assert "NFP" in md


def test_markdown_includes_network_stress_metrics():
    dossier = build_crisis_dossier("2008Q4")
    md = render_dossier_markdown(dossier)
    nss = dossier["network_stress_summary"]
    assert "DebtRank" in md
    assert nss["seed_node"] in md
    assert "Banks in network" in md


def test_markdown_includes_research_notes():
    dossier = build_crisis_dossier("2023Q1")
    md = render_dossier_markdown(dossier)
    # research_notes text shouldn't be HTML-escaped or modified
    snippet = dossier["research_notes"][:40]
    assert snippet in md


def test_markdown_includes_spec_versions():
    dossier = build_crisis_dossier("2008Q4")
    md = render_dossier_markdown(dossier)
    assert "Dossier version" in md
    assert "Fixture version" in md
    assert "Renderer version" in md
    assert REPORT_RENDERER_VERSION in md


def test_markdown_includes_nfa_disclaimer():
    md = render_dossier_markdown(build_crisis_dossier("2008Q4"))
    assert NFA_DISCLAIMER in md
    assert "not financial advice" in md.lower()


def test_markdown_title_prefix_prepends():
    md = render_dossier_markdown(
        build_crisis_dossier("2008Q4"), title_prefix="CBSRM Demo"
    )
    assert md.startswith("# CBSRM Demo — 2008Q4")


# ─── Determinism ──────────────────────────────────────────────────


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_markdown_is_deterministic(window_id):
    a = render_dossier_markdown(build_crisis_dossier(window_id))
    b = render_dossier_markdown(build_crisis_dossier(window_id))
    assert a == b


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_payload_is_deterministic_under_json_serialization(window_id):
    a = json.dumps(build_report_payload(build_crisis_dossier(window_id)),
                   sort_keys=True)
    b = json.dumps(build_report_payload(build_crisis_dossier(window_id)),
                   sort_keys=True)
    assert a == b


# ─── JSON payload ─────────────────────────────────────────────────


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_payload_schema(window_id):
    payload = build_report_payload(build_crisis_dossier(window_id))
    assert set(payload.keys()) == {"report", "dossier"}
    assert payload["report"]["renderer_version"] == REPORT_RENDERER_VERSION
    assert payload["report"]["kind"] == "crisis_window_dossier"
    assert "not financial advice" in payload["report"]["disclaimer"].lower()


@pytest.mark.parametrize("window_id", list(CRISIS_DOSSIER_WINDOWS))
def test_payload_round_trips_through_json_dumps(window_id):
    payload = build_report_payload(build_crisis_dossier(window_id))
    s = json.dumps(payload)
    restored = json.loads(s)
    assert restored["report"]["renderer_version"] == REPORT_RENDERER_VERSION
    assert restored["dossier"]["window_id"] == window_id


def test_payload_sanitizes_numpy_scalars():
    """Inject a numpy scalar into a dossier copy and verify the payload
    still json-serializes cleanly (no TypeError)."""
    d = build_crisis_dossier("2008Q4")
    # network_stress_summary['debt_rank'] is already a float; replace with
    # a numpy float64 to stress the sanitizer path.
    d_copy = dict(d)
    d_copy["network_stress_summary"] = dict(d["network_stress_summary"])
    d_copy["network_stress_summary"]["debt_rank"] = np.float64(0.4321)
    payload = build_report_payload(d_copy)
    s = json.dumps(payload)
    restored = json.loads(s)
    assert restored["dossier"]["network_stress_summary"]["debt_rank"] == pytest.approx(0.4321)


def test_payload_sanitizes_pandas_timestamp():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["period"] = dict(d["period"])
    d_copy["period"]["start"] = pd.Timestamp("2008-09-15")
    payload = build_report_payload(d_copy)
    s = json.dumps(payload)
    restored = json.loads(s)
    assert "2008-09-15" in restored["dossier"]["period"]["start"]


def test_payload_converts_nan_to_none():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["network_stress_summary"] = dict(d["network_stress_summary"])
    d_copy["network_stress_summary"]["debt_rank"] = float("nan")
    payload = build_report_payload(d_copy)
    s = json.dumps(payload)
    restored = json.loads(s)
    assert restored["dossier"]["network_stress_summary"]["debt_rank"] is None


# ─── Validation ───────────────────────────────────────────────────


def test_render_rejects_non_mapping():
    with pytest.raises(ValueError, match="must be a Mapping"):
        render_dossier_markdown("not a dossier")   # type: ignore[arg-type]


def test_render_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing required key"):
        render_dossier_markdown({"window_id": "2008Q4", "title": "x"})


def test_payload_rejects_non_mapping():
    with pytest.raises(ValueError, match="must be a Mapping"):
        build_report_payload([1, 2, 3])   # type: ignore[arg-type]


def test_payload_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing required key"):
        build_report_payload({"window_id": "x"})


def test_render_rejects_bad_period_shape():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["period"] = "2008-09-15 to 2008-12-31"   # wrong type
    with pytest.raises(ValueError, match="period"):
        render_dossier_markdown(d_copy)


def test_render_rejects_bad_network_stress_summary_shape():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["network_stress_summary"] = "0.52"   # wrong type
    with pytest.raises(ValueError, match="network_stress_summary"):
        render_dossier_markdown(d_copy)


# ─── Empty inner sections handled gracefully ──────────────────────


def test_markdown_handles_empty_macro_events():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["macro_event_scores"] = []
    md = render_dossier_markdown(d_copy)
    # Section heading still present, and explicit (none) placeholder
    assert "## Macro event scores" in md
    assert "_(none)_" in md


def test_markdown_handles_empty_replay_summary():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["replay_summary"] = []
    md = render_dossier_markdown(d_copy)
    assert "## Replay summary" in md
    assert "_(none)_" in md


def test_markdown_handles_empty_dominant_drivers():
    d = build_crisis_dossier("2008Q4")
    d_copy = dict(d)
    d_copy["dominant_drivers"] = []
    md = render_dossier_markdown(d_copy)
    assert "## Phase classification" in md
    assert "_(none)_" in md


# ─── No external I/O ──────────────────────────────────────────────


def test_renderer_module_imports_no_io_clients():
    """Sanity check: the renderer composes pure transformations only.
    No urllib/requests/httpx/socket/sqlite3/subprocess reachable from
    a fresh import.
    """
    import cbsrm.reporting.report_renderer as m
    src = open(m.__file__, encoding="utf-8").read()
    for forbidden in ("urllib", "requests", "httpx", "socket",
                      "sqlite3", "sqlalchemy", "urlopen", "subprocess",
                      "open(",   # no file open in the rendering path itself
                      "Path("):
        # Allow `open(` inside docstrings/comments? Check just code lines.
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]
            if forbidden in stripped:
                # tolerate inside a triple-quoted string (heuristic):
                # if line starts with whitespace + quote or contains '"""' allow it
                if '"""' in line or "'''" in line:
                    continue
                raise AssertionError(
                    f"report_renderer.py must not reference {forbidden!r}; "
                    f"offending line: {line!r}"
                )


# ─── Operator end-to-end example ──────────────────────────────────


def test_end_to_end_dossier_to_markdown_to_payload_to_json():
    """One-call narrative: dossier → markdown → payload → json."""
    dossier = build_crisis_dossier("2023Q1")
    md = render_dossier_markdown(dossier, title_prefix="SaaS demo")
    payload = build_report_payload(dossier)
    s = json.dumps(payload, sort_keys=True)
    restored = json.loads(s)

    assert md.startswith("# SaaS demo — 2023Q1")
    assert restored["report"]["renderer_version"] == REPORT_RENDERER_VERSION
    assert restored["dossier"]["window_id"] == "2023Q1"
    assert NFA_DISCLAIMER in md
    assert "not financial advice" in restored["report"]["disclaimer"].lower()
