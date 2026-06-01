"""
Offline tests for ``cbsrm.diagnostics.live_dossiers``.

Block 2 (2026-05-31) adds a live-data-capable crisis dossier with an
explicit fallback hierarchy and provenance metadata, without touching
the fixture-backed ``build_crisis_dossier``. These tests inject fake
clients + cache so they stay fully offline and deterministic:

  * live path → ``metadata["data_source"] == "live"`` and the inputs are
    written back to the cache.
  * live fail + cache hit → ``data_source == "local_cache"`` + warning.
  * no client + cache hit → ``local_cache``.
  * both fail → a clean ``ValueError`` (no traceback leak).
  * the output dict matches the dossier schema keys.

Run: pytest tests/test_live_dossiers.py -v
"""
from __future__ import annotations

import pytest

from cbsrm.diagnostics import build_crisis_dossier, build_crisis_dossier_live
from cbsrm.diagnostics.crisis_dossiers import get_fixture_snapshot


START, END = "2008-09-15", "2008-12-31"
WINDOW_KEY = f"{START}..{END}"


# ─── fakes ─────────────────────────────────────────────────────────


def _live_inputs() -> dict:
    """A complete, valid live-inputs payload.

    Reuses the canonical 2008Q4 fixture's raw inputs (via the public
    snapshot + the pinned network) so we exercise the real assembly
    pipeline with realistic shapes — without pretending it is fixture
    data inside the live builder.
    """
    snap = get_fixture_snapshot("2008Q4")
    # The snapshot omits the network matrices + price panel values; the
    # live builder needs them, so we supply a small valid toy network and
    # a 2-series price panel covering the window.
    return {
        "title": "Live 2008Q4 — Credit/Liquidity Crisis",
        "period_start": START,
        "period_end": END,
        "shock_summary": snap["shock_summary"],
        "research_notes": snap["research_notes"],
        "sources": snap["sources"],
        "macro_events": snap["macro_events"],
        "price_panel": {
            "SPY_PROXY": {
                "2008-09-29": 120.0, "2008-10-01": 118.0,
                "2008-10-03": 115.0, "2008-10-16": 110.0,
                "2008-11-07": 100.0,
            },
        },
        "network_L": [
            [0.0, 35.0, 25.0, 15.0],
            [30.0, 0.0, 20.0, 10.0],
            [20.0, 18.0, 0.0, 12.0],
            [15.0, 10.0, 8.0, 0.0],
        ],
        "network_E": [15.0, 22.0, 18.0, 25.0],
        "network_h0": [0.80, 0.0, 0.0, 0.0],
        "network_seed_label": "EPICENTRE_BANK",
        "phase_features": snap["phase_features"],
    }


class _FakeClients:
    """fetch_inputs returns a payload, or raises if seeded to fail."""

    def __init__(self, payload=None, raise_exc: Exception | None = None):
        self._payload = payload
        self._raise = raise_exc
        self.calls = 0

    def fetch_inputs(self, start: str, end: str) -> dict:
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._payload


class _FakeCache:
    def __init__(self, seed: dict | None = None):
        self._store: dict[str, dict] = {}
        if seed is not None:
            self._store.update(seed)
        self.set_calls = 0

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: dict) -> None:
        self.set_calls += 1
        self._store[key] = value


# ─── 1. live path ──────────────────────────────────────────────────


def test_live_path_sets_data_source_live_and_writes_cache():
    clients = _FakeClients(payload=_live_inputs())
    cache = _FakeCache()
    dossier = build_crisis_dossier_live(START, END, clients=clients, cache=cache)
    assert dossier["metadata"]["data_source"] == "live"
    assert dossier["metadata"]["warnings"] == []
    assert dossier["metadata"]["window"] == {"start": START, "end": END}
    # The successful live fetch is written back for later degraded runs.
    assert cache.set_calls == 1
    assert cache.get(WINDOW_KEY) is not None


def test_live_path_works_without_a_cache():
    clients = _FakeClients(payload=_live_inputs())
    dossier = build_crisis_dossier_live(START, END, clients=clients)
    assert dossier["metadata"]["data_source"] == "live"


# ─── 2. live fail → cache fallback ─────────────────────────────────


def test_live_fail_with_cache_hit_falls_back_to_local_cache():
    cache = _FakeCache(seed={WINDOW_KEY: _live_inputs()})
    clients = _FakeClients(raise_exc=RuntimeError("FRED 429 rate limit"))
    dossier = build_crisis_dossier_live(START, END, clients=clients, cache=cache)
    assert dossier["metadata"]["data_source"] == "local_cache"
    assert any("live fetch failed" in w for w in dossier["metadata"]["warnings"])
    assert any("429" in w for w in dossier["metadata"]["warnings"])


def test_no_client_with_cache_hit_uses_local_cache():
    cache = _FakeCache(seed={WINDOW_KEY: _live_inputs()})
    dossier = build_crisis_dossier_live(START, END, clients=None, cache=cache)
    assert dossier["metadata"]["data_source"] == "local_cache"
    assert any("no live clients" in w for w in dossier["metadata"]["warnings"])


# ─── 3. both fail → clean ValueError ───────────────────────────────


def test_both_fail_raises_clean_value_error():
    clients = _FakeClients(raise_exc=RuntimeError("OFR 403 forbidden"))
    cache = _FakeCache()  # empty — no hit
    with pytest.raises(ValueError) as ei:
        build_crisis_dossier_live(START, END, clients=clients, cache=cache)
    msg = str(ei.value)
    assert WINDOW_KEY in msg
    assert "no local cache hit" in msg
    # The original exception text is surfaced, not a raw traceback object.
    assert "403" in msg


def test_no_client_no_cache_raises_value_error():
    with pytest.raises(ValueError):
        build_crisis_dossier_live(START, END, clients=None, cache=None)


# ─── 4. schema parity with the fixture builder ─────────────────────


def test_output_matches_dossier_schema_keys():
    clients = _FakeClients(payload=_live_inputs())
    live = build_crisis_dossier_live(START, END, clients=clients)
    fixture = build_crisis_dossier("2008Q4")
    # Every key the fixture dossier exposes is present on the live one
    # (the live one adds a `metadata` block on top).
    assert set(fixture.keys()).issubset(set(live.keys()))
    assert "metadata" in live
    # Core assembled surfaces are populated.
    assert live["phase_label"]
    assert live["network_stress_summary"]["n_banks"] == 4
    assert isinstance(live["macro_event_scores"], list)
    assert len(live["macro_event_scores"]) >= 1


# ─── 5. malformed inputs → ValueError (missing required keys) ──────


def test_incomplete_live_inputs_raise_value_error():
    bad = _live_inputs()
    del bad["network_L"]
    clients = _FakeClients(payload=bad)
    with pytest.raises(ValueError) as ei:
        build_crisis_dossier_live(START, END, clients=clients)
    assert "network_L" in str(ei.value)
