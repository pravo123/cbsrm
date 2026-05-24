"""Tests for the deterministic HTML report renderer.

The HTML renderer is a thin composition over the Markdown renderer plus
the third-party ``markdown`` package, wrapped in a minimal print-ready
HTML shell. These tests pin the externally observable HTML contract:

  * importability (without the optional dep at import time)
  * structural content (window id, title, disclaimer all preserved)
  * stylesheet embedding behaviour
  * ``title_prefix`` propagation
  * deterministic output (same dossier → byte-identical HTML)
  * offline construction (no network during rendering)
  * helpful failure mode when ``markdown`` is missing
  * delegation of validation to the Markdown renderer

The tests deliberately do **not** re-validate the Markdown content
semantics — those are covered by ``tests/test_report_renderer.py``.
"""
from __future__ import annotations

import pytest

# The HTML renderer requires the optional ``markdown`` package at call
# time. We import the renderer at module level (it does not import
# ``markdown`` at import time — only inside the function body) and let
# tests that actually render skip cleanly if ``markdown`` is absent.
from cbsrm.diagnostics import build_crisis_dossier, list_dossier_windows
from cbsrm.reporting import (
    HTML_RENDERER_VERSION,
    render_dossier_html,
)


# ─── module-level surface ───────────────────────────────────────────


def test_html_renderer_module_imports_without_markdown(monkeypatch):
    """Simply importing the renderer must not require ``markdown`` —
    the dependency is lazy. We confirm by reloading the module while
    ``markdown`` is masked, mimicking an environment without the
    optional extra."""
    import importlib
    import sys

    # Mask ``markdown`` even if installed.
    monkeypatch.setitem(sys.modules, "markdown", None)

    # Reload the renderer module; this must not raise.
    mod = importlib.reload(
        sys.modules["cbsrm.reporting.html_renderer"]
    )
    assert hasattr(mod, "render_dossier_html")


def test_html_renderer_version_is_semver_like():
    parts = HTML_RENDERER_VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts), HTML_RENDERER_VERSION


# ─── helpful failure when markdown is missing ───────────────────────


def test_render_dossier_html_raises_runtimeerror_when_markdown_missing(
    monkeypatch,
):
    """Calling the renderer without ``markdown`` installed must raise
    a friendly RuntimeError with the install hint."""
    import sys

    monkeypatch.setitem(sys.modules, "markdown", None)

    dossier = build_crisis_dossier("2008Q4")
    with pytest.raises(RuntimeError) as exc:
        render_dossier_html(dossier)
    msg = str(exc.value)
    assert "markdown" in msg.lower()
    assert "cbsrm[html]" in msg


# ─── happy paths (require markdown installed) ───────────────────────


pytest.importorskip("markdown")


@pytest.mark.parametrize("window", list_dossier_windows())
def test_render_dossier_html_returns_str_for_each_window(window):
    dossier = build_crisis_dossier(window)
    html = render_dossier_html(dossier)
    assert isinstance(html, str)
    assert len(html) > 0


def test_render_dossier_html_contains_window_id():
    dossier = build_crisis_dossier("2008Q4")
    html = render_dossier_html(dossier)
    assert "2008Q4" in html


def test_render_dossier_html_contains_title():
    dossier = build_crisis_dossier("2020Q1")
    html = render_dossier_html(dossier)
    # The dossier title must appear in the body and the <title> tag.
    assert dossier["title"] in html
    assert "<title>" in html
    assert "</title>" in html


def test_render_dossier_html_preserves_disclaimer():
    dossier = build_crisis_dossier("2008Q4")
    html = render_dossier_html(dossier)
    assert "Disclaimer" in html


def test_render_dossier_html_embeds_stylesheet_by_default():
    dossier = build_crisis_dossier("2008Q4")
    html = render_dossier_html(dossier)
    assert "<style>" in html
    assert "</style>" in html
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "<head>" in html
    assert "<body>" in html


def test_render_dossier_html_can_skip_stylesheet():
    dossier = build_crisis_dossier("2008Q4")
    html = render_dossier_html(dossier, embed_stylesheet=False)
    # Body-only fragment — no DOCTYPE, no <html>, no <style>, no <body>.
    assert "<!DOCTYPE html>" not in html
    assert "<html" not in html
    assert "<style>" not in html
    assert "<body>" not in html
    # But the rendered content is still there.
    assert "2008Q4" in html


def test_render_dossier_html_title_prefix_applies():
    dossier = build_crisis_dossier("2008Q4")
    html = render_dossier_html(dossier, title_prefix="WAVERVANIR")
    assert "WAVERVANIR" in html
    # The prefix must appear both in the <title> element (for the
    # browser tab / saved-PDF default filename) and in the body H1.
    title_block = html.split("</title>")[0]
    assert "WAVERVANIR" in title_block


def test_render_dossier_html_is_deterministic():
    """Two calls with the same dossier must produce byte-identical
    HTML output."""
    dossier = build_crisis_dossier("2008Q4")
    h1 = render_dossier_html(dossier)
    h2 = render_dossier_html(dossier)
    assert h1 == h2


def test_render_dossier_html_is_offline(monkeypatch):
    """Rendering must not touch the network. We monkeypatch the two
    common HTTP entry points to raise, then call the renderer."""
    import urllib.request

    def _no_urlopen(*_a, **_kw):  # pragma: no cover - defensive
        raise AssertionError("HTML renderer made a urllib network call")

    monkeypatch.setattr(urllib.request, "urlopen", _no_urlopen)

    try:
        import requests  # noqa: F401

        def _no_requests(self, *_a, **_kw):  # pragma: no cover
            raise AssertionError(
                "HTML renderer made a requests network call"
            )

        monkeypatch.setattr("requests.Session.request", _no_requests)
    except ImportError:
        pass

    dossier = build_crisis_dossier("2023Q1")
    html = render_dossier_html(dossier)
    assert "2023Q1" in html


def test_render_dossier_html_validates_input():
    """Validation is delegated to the Markdown renderer; non-Mapping
    and missing-key inputs must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        render_dossier_html("not a dossier")  # type: ignore[arg-type]
    with pytest.raises((ValueError, KeyError, TypeError)):
        render_dossier_html({})
