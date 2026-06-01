"""
Live-data crisis dossiers.
==========================

A live-data-capable sibling of
:func:`cbsrm.diagnostics.crisis_dossiers.build_crisis_dossier`. Where the
fixture builder pins deterministic illustrations for three canonical
windows, this builder sources its macro inputs from *injected* data
clients (FRED / ECB / OFR — they already accept ``session`` +
``cache_dir``) and assembles the **same dossier shape** through the same
shared helpers (``score_event`` → ``replay_macro_events`` →
``debt_rank`` → ``classify_phase``).

The contract is operator-/test-friendly and fully offline-testable:

* ``clients`` — an object exposing ``fetch_inputs(start, end) -> dict``.
  The returned dict supplies the same fields a ``_CrisisFixture`` carries
  (``title``, ``shock_summary``, ``macro_events``, ``price_panel``,
  ``network_L/E/h0``, ``network_seed_label``, ``phase_features``,
  ``research_notes``, ``sources``). Production wiring composes the real
  ``cbsrm.data`` adapters behind this; tests inject a fake.
* ``cache`` — an optional object exposing ``get(key) -> dict | None``
  (and, when a live fetch succeeds, ``set(key, value)`` is called so the
  next degraded run can fall back). Reuses the existing client
  ``.cbsrm_cache/`` story; tests inject a fake.

Fallback hierarchy (recorded in ``metadata["data_source"]``):

* live fetch succeeds                       → ``"live"``
* live fetch fails but cache hit            → ``"local_cache"`` (+ a
  human-readable ``warnings`` list explaining the degrade)
* live fetch fails *and* no cache           → a structured
  :class:`ValueError` (no traceback leak at CLI/API layer)

The fixture-backed :func:`build_crisis_dossier` is left untouched; this
module only adds a new surface. CLI / API wiring is deferred until the
builder itself is green.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cbsrm.diagnostics.crisis_dossiers import (
    DOSSIER_VERSION,
    FIXTURE_VERSION,
    _CrisisFixture,
    build_crisis_dossier,
)


LIVE_DOSSIER_VERSION = "1.0.0"


@runtime_checkable
class _LiveClients(Protocol):
    """Minimal surface the live builder needs from its data clients."""

    def fetch_inputs(self, start: str, end: str) -> dict[str, Any]:
        ...


@runtime_checkable
class _DossierCache(Protocol):
    """Minimal cache surface — a get/set keyed by the window string."""

    def get(self, key: str) -> dict[str, Any] | None:
        ...

    def set(self, key: str, value: dict[str, Any]) -> None:
        ...


_REQUIRED_INPUT_KEYS = (
    "macro_events",
    "price_panel",
    "network_L",
    "network_E",
    "network_h0",
    "network_seed_label",
    "phase_features",
)


def _window_key(start: str, end: str) -> str:
    return f"{start}..{end}"


def _inputs_to_fixture(window_id: str, inputs: dict[str, Any]) -> _CrisisFixture:
    """Coerce a live/cached inputs dict into the ``_CrisisFixture`` the
    shared assembly pipeline consumes. Missing optional narrative fields
    fall back to neutral defaults so the dossier still composes."""
    missing = [k for k in _REQUIRED_INPUT_KEYS if k not in inputs]
    if missing:
        raise ValueError(
            f"live dossier inputs for {window_id!r} missing required "
            f"keys: {missing}"
        )
    return _CrisisFixture(
        window_id=window_id,
        title=inputs.get("title", f"Live crisis dossier {window_id}"),
        period_start=inputs.get("period_start", window_id.split("..")[0]),
        period_end=inputs.get("period_end", window_id.split("..")[-1]),
        shock_summary=inputs.get("shock_summary", ""),
        research_notes=inputs.get("research_notes", ""),
        sources=tuple(inputs.get("sources", ())),
        macro_events=tuple(inputs["macro_events"]),
        price_panel=dict(inputs["price_panel"]),
        network_L=tuple(tuple(float(x) for x in row)
                        for row in inputs["network_L"]),
        network_E=tuple(float(x) for x in inputs["network_E"]),
        network_h0=tuple(float(x) for x in inputs["network_h0"]),
        network_seed_label=inputs["network_seed_label"],
        phase_features=dict(inputs["phase_features"]),
    )


def build_crisis_dossier_live(
    start: str,
    end: str,
    *,
    clients: _LiveClients | None = None,
    cache: _DossierCache | None = None,
) -> dict[str, Any]:
    """Build a live-data crisis dossier for the ``[start, end]`` window.

    Parameters
    ----------
    start, end :
        ISO ``YYYY-MM-DD`` window bounds. Used as the dossier
        ``window_id`` (``"start..end"``) and as the cache key.
    clients :
        Object exposing ``fetch_inputs(start, end) -> dict`` (see module
        docstring for the required input keys). When ``None`` the live
        path is treated as unavailable and the builder goes straight to
        the cache fallback.
    cache :
        Optional object exposing ``get(key)`` / ``set(key, value)``. On a
        successful live fetch the inputs are written back via ``set`` so a
        later degraded run can serve ``local_cache``.

    Returns
    -------
    dict
        The same dossier schema as :func:`build_crisis_dossier`, plus a
        ``metadata`` block recording ``data_source`` (``"live"`` |
        ``"local_cache"``), a ``warnings`` list, and the window bounds.

    Raises
    ------
    ValueError
        When the live fetch fails (or no client is supplied) *and* there
        is no cache hit — a clean, structured error with no traceback
        leak for the CLI/API layer to surface.
    """
    window_id = _window_key(start, end)
    warnings: list[str] = []
    inputs: dict[str, Any] | None = None
    data_source: str | None = None
    live_error: str | None = None

    # 1) Live path.
    if clients is not None:
        try:
            inputs = clients.fetch_inputs(start, end)
            data_source = "live"
            if cache is not None:
                try:
                    cache.set(window_id, inputs)
                except Exception:  # pragma: no cover - cache write best-effort
                    pass
        except Exception as exc:  # live fail / rate-limit / 403
            live_error = f"{type(exc).__name__}: {exc}"
            warnings.append(
                f"live fetch failed ({live_error}); attempting local cache"
            )
    else:
        warnings.append("no live clients supplied; attempting local cache")

    # 2) Cache fallback.
    if inputs is None and cache is not None:
        cached = cache.get(window_id)
        if cached is not None:
            inputs = cached
            data_source = "local_cache"

    # 3) Both failed → structured error (no traceback leak upstream).
    if inputs is None:
        raise ValueError(
            "live crisis dossier unavailable for window "
            f"{window_id}: live fetch {'errored' if live_error else 'unavailable'}"
            f"{' (' + live_error + ')' if live_error else ''} "
            "and no local cache hit"
        )

    # 4) Assemble through the shared, deterministic pipeline.
    fixture = _inputs_to_fixture(window_id, inputs)
    dossier = build_crisis_dossier(window_id, fixtures={window_id: fixture})

    # 5) Stamp provenance / fallback metadata.
    dossier["metadata"] = {
        "data_source": data_source,
        "warnings": warnings,
        "window": {"start": start, "end": end},
        "live_dossier_version": LIVE_DOSSIER_VERSION,
    }
    dossier["spec"]["fixture_version"] = FIXTURE_VERSION
    dossier["spec"]["dossier_version"] = DOSSIER_VERSION
    return dossier


__all__ = [
    "build_crisis_dossier_live",
    "LIVE_DOSSIER_VERSION",
]
