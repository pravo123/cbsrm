"""
Hosting-hardening tests for ``cbsrm.api.routes.build_app``.

Block 6 (2026-05-31) made ``build_app`` safe to host publicly while
staying fully backward-compatible: every new behaviour is opt-in via a
keyword arg, so the default ``build_app()`` is unchanged (open, no
token, no CORS, no rate limit).

Covered:
  * X-Request-ID on every response (always on) — echoed or generated.
  * auth_token → protected endpoints 401 without/with-bad token, 200 with
    ``Bearer <token>``; read-only endpoints stay open; the plain JSON
    dossier (no ?audit/?store) stays open.
  * rate_limit_per_min → 429 once the per-IP window is exceeded; the
    429 still carries an X-Request-ID.
  * allowed_origins → CORS headers obey the configured origin.

Run: pytest tests/test_api_hardening.py -v
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402  (after importorskip)

from cbsrm.api.routes import build_app


# ─── X-Request-ID (always on) ──────────────────────────────────────


def test_request_id_present_on_every_response():
    client = TestClient(build_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")


def test_request_id_echoes_inbound_header():
    client = TestClient(build_app())
    r = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers.get("X-Request-ID") == "trace-abc-123"


def test_request_id_generated_when_absent_is_unique():
    client = TestClient(build_app())
    a = client.get("/health").headers["X-Request-ID"]
    b = client.get("/health").headers["X-Request-ID"]
    assert a != b


# ─── auth_token gating ─────────────────────────────────────────────


def test_default_app_has_no_auth():
    """Back-compat: no auth_token → protected endpoints stay open."""
    client = TestClient(build_app())
    assert client.post("/audit/verify").status_code == 200


def test_protected_endpoint_401_without_token():
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.post("/audit/verify")
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "missing or invalid bearer token"


def test_protected_endpoint_401_with_bad_token():
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.post("/audit/verify",
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_protected_endpoint_200_with_valid_token():
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.post("/audit/verify",
                    headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert r.json()["chain_ok"] is True


def test_read_only_endpoints_stay_open_under_auth():
    """Catalog/health GETs must NOT require the token."""
    client = TestClient(build_app(auth_token="s3cret"))
    assert client.get("/health").status_code == 200
    assert client.get("/reports").status_code == 200
    assert client.get("/reports/crisis-dossiers").status_code == 200


def test_plain_json_dossier_stays_open_under_auth():
    """The plain read-only dossier (no ?audit/?store) is not gated."""
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.get("/reports/crisis-dossiers/2008Q4")
    assert r.status_code == 200


def test_dossier_with_audit_flag_requires_token():
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.get("/reports/crisis-dossiers/2008Q4?audit=true")
    assert r.status_code == 401
    r2 = client.get("/reports/crisis-dossiers/2008Q4?audit=true",
                    headers={"Authorization": "Bearer s3cret"})
    assert r2.status_code == 200
    assert "audit" in r2.json()


def test_stored_artifact_lookup_requires_token():
    """The report-store lookup is gated even before the 'not
    configured' / 'not found' checks."""
    client = TestClient(build_app(auth_token="s3cret"))
    r = client.get("/reports/stored/deadbeef")
    assert r.status_code == 401


# ─── rate limiting ─────────────────────────────────────────────────


def test_rate_limit_returns_429_over_threshold():
    client = TestClient(build_app(rate_limit_per_min=3))
    codes = [client.get("/health").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


def test_rate_limited_response_carries_request_id():
    client = TestClient(build_app(rate_limit_per_min=1))
    client.get("/health")
    r = client.get("/health")
    assert r.status_code == 429
    assert r.headers.get("X-Request-ID")


def test_no_rate_limit_by_default():
    client = TestClient(build_app())
    codes = [client.get("/health").status_code for _ in range(20)]
    assert all(c == 200 for c in codes)


# ─── CORS ──────────────────────────────────────────────────────────


def test_cors_headers_present_when_origin_configured():
    client = TestClient(build_app(allowed_origins=["https://app.example"]))
    r = client.get("/health",
                   headers={"Origin": "https://app.example"})
    assert r.status_code == 200
    assert (
        r.headers.get("access-control-allow-origin")
        == "https://app.example"
    )


def test_no_cors_headers_by_default():
    client = TestClient(build_app())
    r = client.get("/health", headers={"Origin": "https://app.example"})
    assert "access-control-allow-origin" not in r.headers
