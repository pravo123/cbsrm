"""
Offline tests for cbsrm.diagnostics.LiveDossierClients.

Block 2 CLI/API (2026-05-31) adds the concrete client adapter that feeds
``build_crisis_dossier_live``. The price panel is sourced live (FRED);
macro/network/phase layers are pinned from a crisis fixture. These tests
inject a FAKE FRED client returning a tiny pandas Series — fully offline.

Run: pytest tests/test_live_dossier_clients.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from cbsrm.diagnostics import LiveDossierClients, build_crisis_dossier_live


START, END = "2008-09-15", "2008-12-31"


class _FakeFRED:
    """get_series → a small pandas Series; raises if seeded to fail."""

    def __init__(self, raise_exc: Exception | None = None):
        self._raise = raise_exc
        self.calls: list[str] = []

    def get_series(self, series_id, *, observation_start=None,
                   observation_end=None, **_kw):
        self.calls.append(series_id)
        if self._raise is not None:
            raise self._raise
        idx = pd.to_datetime(["2008-09-29", "2008-10-15", "2008-11-07"])
        base = 100.0 if series_id == "SP500" else 95.0
        return pd.Series([base, base - 5, base - 12], index=idx, name=series_id)


# ─── fetch_inputs ──────────────────────────────────────────────────


def test_fetch_inputs_returns_all_builder_required_keys():
    clients = LiveDossierClients(fred=_FakeFRED(), network_window="2008Q4")
    inputs = clients.fetch_inputs(START, END)
    required = {
        "macro_events", "price_panel", "network_L", "network_E",
        "network_h0", "network_seed_label", "phase_features",
    }
    assert required.issubset(set(inputs.keys()))
    # Price panel is live (two FRED series → two panel columns).
    assert set(inputs["price_panel"].keys()) == {"SPY_PROXY", "TLT_PROXY"}
    assert inputs["price_panel"]["SPY_PROXY"]  # non-empty mapping


def test_fetch_inputs_labels_live_vs_fixture_split():
    clients = LiveDossierClients(fred=_FakeFRED(), network_window="2008Q4")
    inputs = clients.fetch_inputs(START, END)
    # Provenance honesty: research_notes + sources name the live FRED panel
    # and the pinned fixture layers.
    assert "LIVE price panel from FRED" in inputs["research_notes"]
    assert any("FRED" in s for s in inputs["sources"])


def test_fetch_inputs_propagates_fred_failure():
    clients = LiveDossierClients(
        fred=_FakeFRED(raise_exc=RuntimeError("FRED 429")),
        network_window="2008Q4",
    )
    with pytest.raises(RuntimeError):
        clients.fetch_inputs(START, END)


def test_unknown_network_window_raises():
    with pytest.raises(ValueError):
        LiveDossierClients(fred=_FakeFRED(), network_window="NOPE")


# ─── end-to-end through the builder ────────────────────────────────


def test_builder_with_live_clients_data_source_live():
    clients = LiveDossierClients(fred=_FakeFRED(), network_window="2008Q4")
    dossier = build_crisis_dossier_live(START, END, clients=clients)
    assert dossier["metadata"]["data_source"] == "live"
    assert dossier["network_stress_summary"]["n_banks"] == 4
    assert dossier["phase_label"]


def test_builder_fred_fail_no_cache_raises_value_error():
    clients = LiveDossierClients(
        fred=_FakeFRED(raise_exc=RuntimeError("FRED 403")),
        network_window="2008Q4",
    )
    with pytest.raises(ValueError):
        build_crisis_dossier_live(START, END, clients=clients, cache=None)
