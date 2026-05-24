"""
cbsrm.reporting.html_renderer — deterministic HTML export of crisis-window
dossiers, suitable for browser print-to-PDF.

Design contract
~~~~~~~~~~~~~~~

* **Composition over duplication.** The Markdown body is produced by
  :func:`cbsrm.reporting.report_renderer.render_dossier_markdown` (no
  changes there) and then piped through the ``markdown`` library to
  produce HTML.  No alternative dossier-walk implementation.
* **Deterministic.** Same dossier in → same HTML out.  Safe for
  snapshot tests and for stable demo screenshots / print-to-PDF.
* **Offline.** No network, no filesystem writes, no PDF lib.
* **Browser print-to-PDF, not a binary PDF byte stream.** This module
  produces HTML suitable for "File → Print → Save as PDF" in a modern
  browser.  A real ``.pdf`` byte stream (via reportlab / weasyprint)
  is deferred to a separate slice with its own dependency review.

Optional dependency
~~~~~~~~~~~~~~~~~~~

The ``markdown`` package (≥ 3.5, < 4) is loaded lazily inside
:func:`render_dossier_html`.  Install with ``pip install cbsrm[html]``.
Importing this module itself does **not** require ``markdown`` to be
installed; only calling the renderer does.

Public surface (v0.9 work in progress)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* :func:`render_dossier_html` — render a crisis-window dossier as a
  deterministic HTML report, with an optional embedded print-friendly
  stylesheet.
* :data:`HTML_RENDERER_VERSION` — semantic version of the HTML
  renderer spec (independent of the Markdown renderer + dossier).
"""
from __future__ import annotations

import html as _html
from typing import Any, Mapping

from cbsrm.reporting.report_renderer import render_dossier_markdown


HTML_RENDERER_VERSION = "1.0.0"


# Print-friendly stylesheet for browser "File -> Print -> Save as PDF".
# Adapted from the project's existing whitepaper print-style approach
# (see tools/build_whitepaper_html.py).  Kept self-contained so callers
# do not need to ship a separate CSS file.
_PRINT_STYLESHEET = """\
@page { size: letter; margin: 1in; }
@media print {
  h1 { page-break-after: avoid; }
  h2 { page-break-before: always; page-break-after: avoid; }
  h2:first-of-type { page-break-before: avoid; }
  h3 { page-break-after: avoid; }
  pre, blockquote, table { page-break-inside: avoid; }
}
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Times New Roman", Times, serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #0e1116;
  max-width: 7.5in;
  margin: 0 auto;
  padding: 0.5in;
}
h1, h2, h3, h4 {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #0e1116;
}
h1 { font-size: 22pt; margin-top: 0; }
h2 { font-size: 15pt; border-bottom: 1px solid #d0d7de; padding-bottom: 4pt; }
h3 { font-size: 12pt; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
th, td { border: 1px solid #d0d7de; padding: 4pt 6pt; text-align: left; }
th { background: #f6f8fa; }
code { font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 0.95em; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 1em 0; }
"""


def _require_markdown():
    """Import the ``markdown`` package or raise a friendly RuntimeError.

    Kept as a helper so tests can monkeypatch the import path
    cleanly via ``sys.modules['markdown'] = None``.
    """
    try:
        import markdown  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised in tests
        raise RuntimeError(
            "HTML rendering requires the `markdown` package. "
            "Install with: pip install cbsrm[html]"
        ) from exc
    import markdown as _md
    return _md


def render_dossier_html(
    dossier: Mapping[str, Any],
    *,
    title_prefix: str | None = None,
    embed_stylesheet: bool = True,
) -> str:
    """Render a crisis-window dossier as deterministic HTML.

    Composition: :func:`render_dossier_markdown` -> ``markdown`` library
    -> HTML body, optionally wrapped in a minimal
    ``<html><head><style>...</style></head><body>...</body></html>``
    shell with a print-friendly stylesheet.

    Parameters
    ----------
    dossier :
        Output of :func:`cbsrm.diagnostics.crisis_dossiers.build_crisis_dossier`.
    title_prefix :
        Optional string prepended to the report title. Passed straight
        through to the Markdown renderer.
    embed_stylesheet :
        When True (default), return a complete HTML document with the
        print-friendly stylesheet embedded in ``<head>``.  When False,
        return only the rendered ``<body>``-content fragment so the
        caller can compose it into a larger document.

    Returns
    -------
    str
        Deterministic HTML.  Same dossier in -> same HTML out.

    Raises
    ------
    ValueError
        If the dossier is malformed (delegates to the Markdown
        renderer's validation).
    RuntimeError
        If the optional ``markdown`` package is not installed.
    """
    md_lib = _require_markdown()

    markdown_body = render_dossier_markdown(
        dossier, title_prefix=title_prefix,
    )
    # ``markdown.markdown`` is a pure function over the input string.
    # The "tables" extension is required because the dossier emits
    # GitHub-style tables for macro events and the replay surface.
    html_body = md_lib.markdown(
        markdown_body,
        extensions=["tables"],
        output_format="html",
    )

    if not embed_stylesheet:
        return html_body

    # Build the HTML <title> from the dossier so the saved-PDF default
    # filename in browsers is meaningful.
    raw_title = dossier["title"]
    if title_prefix:
        raw_title = f"{title_prefix} \u2014 {raw_title}"
    escaped_title = _html.escape(raw_title, quote=False)

    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{escaped_title}</title>\n"
        "<style>\n"
        f"{_PRINT_STYLESHEET}"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{html_body}\n"
        "</body>\n"
        "</html>\n"
    )
