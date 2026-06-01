"""
Tests for the live-data crisis-dossier API routes (Block 2 CLI/API).

The handler builds its client adapter via the module-level factory
``cbsrm.api.routes._make_live_clients`` — these tests monkeypatch that
factory with a fake (fed by a fake FRED), so they never touch the network.
Covers the happy path + metadata, the clean 502 on live failure, and the
bearer-token gate (this is a heavy/network endpoint).

Run: pytest tests/test_api_crisis_dossiers_live.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import cbsrm.api.routes as routes  # noqa: E402
from cbsrm.api.routes import build_app  # noqa: E402
from cbsrm.diagnostics import LiveDossierClients  # noqa: E402


START, END = "2008-09-15", "2008-12-31"


class _FakeFRED:
    def __init__(self, raise_exc: Exception | None = None):
        self._raise = raise_exc

    def get_series(self, series_id, *, observation_start=None,
                   observation_end=None, **_kw):
        if self._raise is not None:
            raise self._raise
        idx = pd.to_datetime(["2008-09-29", "2008-10-15", "2008-11-07"])
        base = 100.0 if series_id == "SP500" else 95.0
        return pd.Series([base, base - 5, base - 12], index=idx, name=series_id)


def _patch_factory(monkeypatch, fred):
    def _fake(network_window: str):
        return LiveDossierClients(fred=fred, network_window=network_window)

    monkeypatch.setattr(routes, "_make_live_clients", _fake)


# ─── route registration ────────────────────────────────────────────


def test_live_routes_registered():
    app = build_app()
    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/reports/crisis-dossiers-live" in paths
    assert "/reports/crisis-dossiers-live/markdown" in paths


# ─── happy path ────────────────────────────────────────────────────


def test_live_json_returns_200_with_metadata(monkeypatch):
    _patch_factory(monkeypatch, _FakeFRED())
    client = TestClient(build_app())
    r = client.get(f"/reports/crisis-dossiers-live?start={START}&end={END}")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"report", "dossier"}
    assert body["dossier"]["metadata"]["data_source"] == "live"


def test_live_markdown_returns_text(monkeypatch):
    _patch_factory(monkeypatch, _FakeFRED())
    client = TestClient(build_app())
    r = client.get(
        f"/reports/crisis-dossiers-live/markdown?start={START}&end={END}")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "# " in r.text  # a markdown title


# ─── live failure → clean 502 ──────────────────────────────────────


def test_live_failure_returns_clean_502(monkeypatch):
    _patch_factory(monkeypatch, _FakeFRED(raise_exc=RuntimeError("FRED 403")))
    client = TestClient(build_app())
    r = client.get(f"/reports/crisis-dossiers-live?start={START}&end={END}")
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "live data unavailable"
    assert "Traceback" not in r.text


# ─── auth gating (heavy endpoint) ──────────────────────────────────


def test_live_requires_token_when_configured(monkeypatch):
    _patch_factory(monkeypatch, _FakeFRED())
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.get(f"/reports/crisis-dossiers-live?start={START}&end={END}")
    assert r.status_code == 401
    r2 = client.get(
        f"/reports/crisis-dossiers-live?start={START}&end={END}",
        headers={"Authorization": "Bearer s3cret"},
    )
    assert r2.status_code == 200


def test_live_open_when_no_token(monkeypatch):
    _patch_factory(monkeypatch, _FakeFRED())
    client = TestClient(build_app())
    r = client.get(f"/reports/crisis-dossiers-live?start={START}&end={END}")
    assert r.status_code == 200
