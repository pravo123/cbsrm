"""
Tests for the headless PDF dossier renderer.

Block 4 (2026-05-31) adds an optional ReportLab-backed PDF surface
(``cbsrm[pdf]``). These tests assert structural PDF properties — header,
EOF trailer, non-trivial length, file write, and dual input shapes
(dossier dict or report payload) — rather than a byte hash (ReportLab
embeds internal object ids that are not byte-reproducible).

Run: pytest tests/test_pdf_renderer.py -v
"""
from __future__ import annotations

import pytest

pytest.importorskip("reportlab")

from cbsrm.diagnostics import build_crisis_dossier
from cbsrm.reporting import build_report_payload, render_dossier_pdf
from cbsrm.reporting.pdf_renderer import PDF_RENDERER_VERSION


@pytest.fixture
def dossier() -> dict:
    return build_crisis_dossier("2008Q4")


def test_returns_pdf_bytes_with_header_and_eof(dossier):
    out = render_dossier_pdf(dossier)
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF")
    assert b"%%EOF" in out
    assert len(out) > 1000


def test_accepts_payload_envelope(dossier):
    payload = build_report_payload(dossier)
    out = render_dossier_pdf(payload)
    assert out.startswith(b"%PDF")
    assert len(out) > 1000


def test_output_path_writes_identical_bytes(dossier, tmp_path):
    p = tmp_path / "dossier.pdf"
    out = render_dossier_pdf(dossier, output_path=p)
    assert p.exists()
    assert p.read_bytes() == out
    assert p.read_bytes().startswith(b"%PDF")


def test_all_windows_render(dossier):
    from cbsrm.diagnostics import list_dossier_windows

    for w in list_dossier_windows():
        out = render_dossier_pdf(build_crisis_dossier(w))
        assert out.startswith(b"%PDF")


def test_non_mapping_input_raises():
    with pytest.raises(ValueError):
        render_dossier_pdf("not a dossier")  # type: ignore[arg-type]


def test_version_constant_is_semver():
    assert PDF_RENDERER_VERSION.count(".") == 2
