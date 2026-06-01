"""
Headless PDF renderer for crisis-window dossiers.
=================================================

Turns a crisis-window dossier (the output of
:func:`cbsrm.diagnostics.build_crisis_dossier` / ``build_crisis_dossier_live``)
into a publication-quality, 3-page executive PDF — entirely headless, no
browser, no network.

The PDF stack is an **optional** extra (``pip install cbsrm[pdf]`` →
ReportLab). The base install is unaffected: this module imports ReportLab
lazily inside :func:`render_dossier_pdf`, mirroring the FastAPI lazy-import
guard in :func:`cbsrm.api.routes.build_app`.

Public surface
~~~~~~~~~~~~~~

* :func:`render_dossier_pdf` — render a dossier (or the
  ``{"report":..., "dossier":...}`` payload) to PDF bytes; optionally also
  write to ``output_path``.
* :data:`PDF_RENDERER_VERSION` — semantic version of the PDF spec.

Layout (3 pages)
~~~~~~~~~~~~~~~~

* **Page 1** — executive summary: title, window/period, shock summary,
  phase classification (label / risk posture / dominant drivers), headline
  DebtRank systemic score.
* **Page 2** — macro event-score table and macro-replay table.
* **Page 3** — network/cascade stress summary, research notes, and the
  canonical NFA disclaimer.

Deterministic content; the only non-reproducible bytes are ReportLab's
internal PDF object ids / timestamps, so tests assert structural properties
(``%PDF`` header, ``%%EOF`` trailer, non-trivial length) rather than a byte
hash.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from cbsrm.reporting.report_renderer import NFA_DISCLAIMER


PDF_RENDERER_VERSION = "1.0.0"


def _require_reportlab():
    """Import ReportLab lazily, with a clear install hint on failure."""
    try:
        from reportlab.lib import colors  # noqa: F401
        from reportlab.lib.pagesizes import LETTER  # noqa: F401
        from reportlab.lib.styles import getSampleStyleSheet  # noqa: F401
        from reportlab.lib.units import inch  # noqa: F401
        from reportlab.platypus import (  # noqa: F401
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as e:  # pragma: no cover - exercised only without extra
        raise RuntimeError(
            "PDF rendering requires ReportLab. Install with: "
            "pip install cbsrm[pdf]"
        ) from e
    import reportlab

    return reportlab


def _normalize_to_dossier(dossier_or_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept either a raw dossier dict or the report payload envelope
    ``{"report":..., "dossier":...}`` and return the inner dossier."""
    if not isinstance(dossier_or_payload, Mapping):
        raise ValueError(
            "pdf_renderer: input must be a Mapping (dossier or payload), "
            f"got {type(dossier_or_payload).__name__}"
        )
    if "dossier" in dossier_or_payload and "window_id" not in dossier_or_payload:
        inner = dossier_or_payload["dossier"]
        if not isinstance(inner, Mapping):
            raise ValueError("pdf_renderer: payload['dossier'] must be a Mapping")
        return inner
    return dossier_or_payload


def _fmt_float(x: Any, places: int = 4) -> str:
    if x is None:
        return "n/a"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(f):
        return "n/a"
    return f"{f:.{places}f}"


def render_dossier_pdf(
    dossier_or_payload: Mapping[str, Any],
    output_path: str | Path | None = None,
) -> bytes:
    """Render a crisis-window dossier to a 3-page executive PDF.

    Parameters
    ----------
    dossier_or_payload :
        Either a dossier dict (``build_crisis_dossier`` output) or the
        ``{"report":..., "dossier":...}`` payload envelope from
        :func:`cbsrm.reporting.build_report_payload`.
    output_path :
        When provided, the PDF bytes are also written to this path. The
        bytes are always returned regardless.

    Returns
    -------
    bytes
        The rendered PDF document.

    Raises
    ------
    RuntimeError
        If ReportLab is not installed (``pip install cbsrm[pdf]``).
    ValueError
        If the input is not a Mapping / dossier-shaped.
    """
    _require_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    dossier = _normalize_to_dossier(dossier_or_payload)

    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    small = styles["Italic"]

    def _table(header: list[str], rows: list[list[str]]):
        data = [header] + rows if rows else [header, ["(none)"] + [""] * (len(header) - 1)]
        t = Table(data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2933")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f2f4f6")]),
                ]
            )
        )
        return t

    story: list[Any] = []

    # ── Page 1 — executive summary ──────────────────────────────────
    title = str(dossier.get("title", "Crisis Dossier"))
    period = dossier.get("period", {}) or {}
    window_id = str(dossier.get("window_id", "n/a"))
    story.append(Paragraph(title, h1))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(
        f"<b>Window:</b> {window_id} &nbsp;&nbsp; "
        f"<b>Period:</b> {period.get('start', 'n/a')} &rarr; "
        f"{period.get('end', 'n/a')}",
        body,
    ))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Shock summary", h2))
    story.append(Paragraph(str(dossier.get("shock_summary") or "(none)"), body))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Phase classification", h2))
    drivers = dossier.get("dominant_drivers") or []
    drivers_str = ", ".join(str(d) for d in drivers) if drivers else "(none)"
    nss = dossier.get("network_stress_summary", {}) or {}
    story.append(Paragraph(
        f"<b>Phase label:</b> {dossier.get('phase_label', 'n/a')}<br/>"
        f"<b>Risk posture:</b> {dossier.get('risk_posture', 'n/a')}<br/>"
        f"<b>Dominant drivers:</b> {drivers_str}<br/>"
        f"<b>DebtRank (systemic R):</b> {_fmt_float(nss.get('debt_rank'), 4)}",
        body,
    ))
    story.append(PageBreak())

    # ── Page 2 — macro tables ───────────────────────────────────────
    story.append(Paragraph("Macro event scores", h2))
    events = dossier.get("macro_event_scores") or []
    ev_rows = [
        [
            str(ev.get("event", "")),
            str(ev.get("release_date", "")),
            _fmt_float(ev.get("actual"), 2),
            _fmt_float(ev.get("consensus"), 2),
            _fmt_float(ev.get("surprise"), 2),
            _fmt_float(ev.get("surprise_z"), 2),
            str(ev.get("direction", "")),
            str(ev.get("severity", "")),
        ]
        for ev in events
    ]
    story.append(_table(
        ["event", "date", "actual", "cons.", "surp.", "z", "dir", "sev"],
        ev_rows,
    ))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Macro replay", h2))
    replay = dossier.get("replay_summary") or []
    rp_rows = [
        [
            str(r.get("event", "")),
            str(r.get("date", "")),
            str(r.get("price_series", "")),
            _fmt_float(r.get("pre_return"), 4),
            _fmt_float(r.get("post_return"), 4),
            str(r.get("direction", "")),
        ]
        for r in replay
    ]
    story.append(_table(
        ["event", "date", "series", "pre_ret", "post_ret", "dir"],
        rp_rows,
    ))
    story.append(PageBreak())

    # ── Page 3 — network / notes / disclaimer ───────────────────────
    story.append(Paragraph("Network stress summary", h2))
    story.append(Paragraph(
        f"<b>Seed node:</b> {nss.get('seed_node', 'n/a')}<br/>"
        f"<b>Banks in network:</b> {nss.get('n_banks', 'n/a')}<br/>"
        f"<b>DebtRank (systemic R):</b> {_fmt_float(nss.get('debt_rank'), 4)}<br/>"
        f"<b>Iterations:</b> {nss.get('iterations', 'n/a')} &nbsp;&nbsp; "
        f"<b>Converged:</b> {nss.get('converged', 'n/a')}",
        body,
    ))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Research notes", h2))
    story.append(Paragraph(str(dossier.get("research_notes") or "(none)"), body))
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("Disclaimer", h2))
    # Strip markdown bold markers for the PDF body (ReportLab uses HTML tags).
    disclaimer = NFA_DISCLAIMER.replace("**", "")
    story.append(Paragraph(disclaimer, small))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=title,
        author="CBSRM",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(story)
    pdf_bytes = buf.getvalue()

    if output_path is not None:
        Path(output_path).write_bytes(pdf_bytes)

    return pdf_bytes


__all__ = [
    "render_dossier_pdf",
    "PDF_RENDERER_VERSION",
]
