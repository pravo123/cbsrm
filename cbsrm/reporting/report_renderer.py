"""
Deterministic Markdown + JSON renderers for crisis-window dossiers.

Takes the output of :func:`cbsrm.diagnostics.crisis_dossiers.build_crisis_dossier`
and turns it into either:

* A clean Markdown research report (human-readable, paper-ready, dashboard
  embeddable) — :func:`render_dossier_markdown`.
* A JSON-serializable payload (storage-ready, API-ready, snapshot-friendly) —
  :func:`build_report_payload`.

Both functions are pure, side-effect-free, and bit-for-bit deterministic given
the same input. No file I/O, no network, no PDF, no web app, no auth, no
billing.

Schema contract
~~~~~~~~~~~~~~~

Input is a *dossier dict* with at minimum these top-level keys (a subset
of the schema produced by ``build_crisis_dossier``)::

    window_id, title, period, shock_summary, macro_event_scores,
    replay_summary, network_stress_summary, phase_label,
    dominant_drivers, risk_posture, research_notes, spec

Missing keys raise :class:`ValueError` with the exact missing-key list.
Empty inner sections (`macro_event_scores=[]`, etc.) are rendered as an
explicit "(none)" placeholder so the report is still well-formed.

NFA disclaimer
~~~~~~~~~~~~~~

Every rendered Markdown report appends a canonical "research only, not
financial advice" footer. Operators who embed the report into a regulated
surface (broker dashboard, customer email, signed PDF) MUST keep the
footer intact; modifying or removing it is out-of-scope for the renderer
contract.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


REPORT_RENDERER_VERSION = "1.0.0"


NFA_DISCLAIMER = (
    "**Disclaimer.** This report is research and decision-intelligence "
    "output from the CBSRM open-source library. It is **not financial "
    "advice**, **not a recommendation to buy or sell any security**, and "
    "**not a regulated investment communication**. All fixtures, model "
    "outputs, and narrative text are illustrative; production users must "
    "independently validate against live data and consult a licensed "
    "professional before acting on any quantitative output."
)


_REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "window_id",
    "title",
    "period",
    "shock_summary",
    "macro_event_scores",
    "replay_summary",
    "network_stress_summary",
    "phase_label",
    "dominant_drivers",
    "risk_posture",
    "research_notes",
    "spec",
)


# ─── Validation ────────────────────────────────────────────────────


def _validate_dossier(dossier: Any) -> Mapping[str, Any]:
    """Validate a dossier dict, returning it as a Mapping for safe access.

    Raises ``ValueError`` on wrong type or missing required keys.
    """
    if not isinstance(dossier, Mapping):
        raise ValueError(
            "report_renderer: dossier must be a Mapping (e.g. dict), "
            f"got {type(dossier).__name__}"
        )
    missing = [k for k in _REQUIRED_TOP_LEVEL_KEYS if k not in dossier]
    if missing:
        raise ValueError(
            f"report_renderer: dossier missing required key(s) {missing!r}; "
            f"expected superset = {list(_REQUIRED_TOP_LEVEL_KEYS)}"
        )

    period = dossier["period"]
    if not isinstance(period, Mapping) or not {"start", "end"}.issubset(period.keys()):
        raise ValueError(
            "report_renderer: dossier['period'] must be a Mapping with "
            "'start' and 'end' keys"
        )

    nss = dossier["network_stress_summary"]
    if not isinstance(nss, Mapping):
        raise ValueError(
            "report_renderer: dossier['network_stress_summary'] must be a Mapping"
        )

    return dossier


# ─── JSON sanitization ────────────────────────────────────────────


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable primitives.

    Handles numpy scalars, numpy arrays, pandas Timestamps, sets,
    tuples, and Mappings. Non-finite floats are emitted as ``None`` so
    the resulting payload always passes through ``json.dumps`` cleanly.
    """
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    # numpy scalars
    if isinstance(obj, np.generic):
        return _to_jsonable(obj.item())
    # numpy arrays
    if isinstance(obj, np.ndarray):
        return [_to_jsonable(x) for x in obj.tolist()]
    # pandas timestamps
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    # mappings
    if isinstance(obj, Mapping):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    # other iterables
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_jsonable(x) for x in obj]
    # fallback: stringify (deterministic; no eval / repr roundtrip)
    return str(obj)


def build_report_payload(dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Build a JSON-serializable payload from a crisis-window dossier.

    The payload mirrors the dossier structure plus a small ``report``
    envelope carrying the renderer version and the canonical disclaimer
    so a downstream API consumer never has to look up either separately.

    The output is guaranteed to round-trip cleanly through
    ``json.dumps(payload)`` — non-finite floats become ``None``, numpy
    scalars become Python scalars, pandas Timestamps become ISO strings,
    and any other object is coerced to its ``str()`` representation.

    Parameters
    ----------
    dossier :
        Output of :func:`cbsrm.diagnostics.crisis_dossiers.build_crisis_dossier`.

    Returns
    -------
    dict
        JSON-serializable payload.
    """
    _validate_dossier(dossier)
    body = _to_jsonable(dossier)
    return {
        "report": {
            "renderer_version": REPORT_RENDERER_VERSION,
            "disclaimer": NFA_DISCLAIMER,
            "kind": "crisis_window_dossier",
        },
        "dossier": body,
    }


# ─── Markdown rendering ───────────────────────────────────────────


def _fmt_float(x: Any, places: int = 4) -> str:
    if x is None:
        return "_n/a_"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(f):
        return "_n/a_"
    return f"{f:.{places}f}"


def _render_macro_event_row(ev: Mapping[str, Any]) -> str:
    return (
        f"| {ev.get('event', '')} "
        f"| {ev.get('release_date', '')} "
        f"| {_fmt_float(ev.get('actual'), 4)} "
        f"| {_fmt_float(ev.get('consensus'), 4)} "
        f"| {_fmt_float(ev.get('surprise'), 4)} "
        f"| {_fmt_float(ev.get('surprise_z'), 2)} "
        f"| {ev.get('direction', '')} "
        f"| {ev.get('severity', '')} "
        f"| {ev.get('risk_bias', '')} |"
    )


def _render_replay_row(row: Mapping[str, Any]) -> str:
    return (
        f"| {row.get('event', '')} "
        f"| {row.get('date', '')} "
        f"| {row.get('price_series', '')} "
        f"| {_fmt_float(row.get('pre_return'), 4)} "
        f"| {_fmt_float(row.get('post_return'), 4)} "
        f"| {row.get('direction', '')} "
        f"| {row.get('risk_bias', '')} |"
    )


def render_dossier_markdown(
    dossier: Mapping[str, Any],
    *,
    title_prefix: str | None = None,
) -> str:
    """Render a crisis-window dossier as a deterministic Markdown report.

    Sections (in order):

    1. Title + window id + period
    2. Shock summary
    3. Phase / risk posture / dominant drivers
    4. Macro event score table
    5. Replay table (event-by-price-series)
    6. Network stress summary
    7. Research notes
    8. Spec / version metadata
    9. NFA disclaimer (footer)

    Parameters
    ----------
    dossier :
        Output of :func:`cbsrm.diagnostics.crisis_dossiers.build_crisis_dossier`.
    title_prefix :
        Optional string prepended to the report title (e.g. a workspace name
        or report kind). Does not alter the dossier itself.

    Returns
    -------
    str
        The Markdown report. Always ends with the NFA disclaimer footer.
    """
    _validate_dossier(dossier)

    title = dossier["title"]
    if title_prefix:
        title = f"{title_prefix} — {title}"

    period = dossier["period"]
    window_id = dossier["window_id"]

    lines: list[str] = []

    # 1) Title
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"**Window:** `{window_id}`  "
        f"**Period:** {period.get('start', '_n/a_')} → {period.get('end', '_n/a_')}"
    )
    lines.append("")

    # 2) Shock summary
    lines.append("## Shock summary")
    lines.append("")
    lines.append(str(dossier.get("shock_summary") or "_(none)_"))
    lines.append("")

    # 3) Phase / posture / drivers
    drivers = dossier.get("dominant_drivers") or []
    drivers_str = ", ".join(f"`{d}`" for d in drivers) if drivers else "_(none)_"
    lines.append("## Phase classification")
    lines.append("")
    lines.append(f"- **Phase label:** `{dossier['phase_label']}`")
    lines.append(f"- **Risk posture:** `{dossier['risk_posture']}`")
    lines.append(f"- **Dominant drivers:** {drivers_str}")
    lines.append("")

    # 4) Macro event scores
    events = dossier.get("macro_event_scores") or []
    lines.append("## Macro event scores")
    lines.append("")
    if not events:
        lines.append("_(none)_")
    else:
        lines.append(
            "| event | release_date | actual | consensus | surprise | "
            "z | direction | severity | risk_bias |"
        )
        lines.append(
            "|---|---|---:|---:|---:|---:|---|---|---|"
        )
        for ev in events:
            lines.append(_render_macro_event_row(ev))
    lines.append("")

    # 5) Replay summary
    replay = dossier.get("replay_summary") or []
    lines.append("## Replay summary")
    lines.append("")
    if not replay:
        lines.append("_(none)_")
    else:
        lines.append(
            "| event | date | price_series | pre_return | post_return | "
            "direction | risk_bias |"
        )
        lines.append("|---|---|---|---:|---:|---|---|")
        for row in replay:
            lines.append(_render_replay_row(row))
    lines.append("")

    # 6) Network stress
    nss = dossier["network_stress_summary"]
    lines.append("## Network stress summary")
    lines.append("")
    if not nss:
        lines.append("_(none)_")
    else:
        lines.append(f"- **Seed node:** `{nss.get('seed_node', '_n/a_')}`")
        lines.append(f"- **Banks in network:** {nss.get('n_banks', '_n/a_')}")
        lines.append(
            f"- **DebtRank (systemic R):** {_fmt_float(nss.get('debt_rank'), 4)}"
        )
        lines.append(
            f"- **Iterations:** {nss.get('iterations', '_n/a_')}  "
            f"**Converged:** {nss.get('converged', '_n/a_')}"
        )
    lines.append("")

    # 7) Research notes
    lines.append("## Research notes")
    lines.append("")
    lines.append(str(dossier.get("research_notes") or "_(none)_"))
    lines.append("")

    # 8) Spec / version metadata
    spec = dossier.get("spec") or {}
    lines.append("## Spec")
    lines.append("")
    lines.append(
        f"- **Dossier version:** `{spec.get('dossier_version', '_n/a_')}`  "
        f"**Fixture version:** `{spec.get('fixture_version', '_n/a_')}`"
    )
    lines.append(
        f"- **Phase rule version:** `{spec.get('phase_rule_version', '_n/a_')}`"
    )
    lines.append(
        f"- **Renderer version:** `{REPORT_RENDERER_VERSION}`"
    )
    composition = spec.get("composition")
    if composition:
        lines.append(f"- **Composition:** `{composition}`")
    sources = spec.get("sources") or []
    if sources:
        lines.append("- **Sources:**")
        for s in sources:
            lines.append(f"  - {s}")
    lines.append("")

    # 9) NFA disclaimer footer
    lines.append("---")
    lines.append("")
    lines.append(NFA_DISCLAIMER)
    lines.append("")

    return "\n".join(lines)


__all__ = [
    "render_dossier_markdown",
    "build_report_payload",
    "REPORT_RENDERER_VERSION",
    "NFA_DISCLAIMER",
]
