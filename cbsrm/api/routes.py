"""
FastAPI service exposing CBSRM indicators.

Run with:
    pip install cbsrm[api]
    uvicorn cbsrm.api.routes:app --reload

Endpoints (v0.1):
    GET  /                      — service info
    GET  /health                — healthz
    GET  /indicators            — list registered indicators
    GET  /indicators/{id}/latest
    GET  /indicators/{id}/series?start=YYYY-MM-DD&end=YYYY-MM-DD
    GET  /audit/{subject}       — audit chain for one subject
    POST /audit/verify          — verify chain integrity

This module intentionally imports FastAPI lazily so that the core
indicator + audit code remains importable in environments without
fastapi installed (e.g. notebooks).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from cbsrm import __version__
from cbsrm.audit.chain import AuditChain


def build_app(audit_conn: sqlite3.Connection | None = None):
    """Construct the FastAPI app. Returns the app instance.

    Pass an audit_conn to share an audit chain across the service; if None
    an in-memory sqlite is used (audit chain non-persistent).
    """
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as e:
        raise RuntimeError(
            "FastAPI not installed. Install with: pip install cbsrm[api]"
        ) from e

    if audit_conn is None:
        audit_conn = sqlite3.connect(":memory:", check_same_thread=False)
    audit = AuditChain(audit_conn)

    app = FastAPI(
        title="CBSRM — Cross-Border Systemic Risk Monitor",
        version=__version__,
        description=(
            "Open-source quantitative framework for cross-jurisdiction "
            "systemic-stress monitoring. Apache-2.0 licensed. "
            "See https://github.com/pravo123/cbsrm for the whitepaper "
            "and methodology details."
        ),
    )

    @app.get("/", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "service": "cbsrm",
            "version": __version__,
            "tier": "public",
            "docs": "/docs",
            "whitepaper": "whitepaper/cbsrm_methodology_v1.md",
            "license": "Apache-2.0",
        }

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/indicators", tags=["indicators"])
    def list_indicators() -> dict[str, Any]:
        from cbsrm.indicators import CISSUS, STLFSIWrap

        registry = [
            {
                "id": STLFSIWrap.id,
                "version": STLFSIWrap.version,
                "source": STLFSIWrap.source,
                "requires": STLFSIWrap().required_series(),
            },
            {
                "id": CISSUS.id,
                "version": CISSUS.version,
                "source": CISSUS.source,
                "requires": CISSUS().required_series(),
            },
        ]
        return {"indicators": registry}

    @app.get("/audit/{subject}", tags=["audit"])
    def get_audit(subject: str, limit: int = 100) -> dict[str, Any]:
        rows = audit.query_subject(subject, limit=limit)
        return {
            "subject": subject,
            "n_rows": len(rows),
            "rows": [
                {
                    "id": r.id, "ts": r.ts, "kind": r.kind,
                    "subject": r.subject, "payload": r.payload,
                    "hash": r.hash, "prev_hash": r.prev_hash,
                }
                for r in rows
            ],
        }

    @app.post("/audit/verify", tags=["audit"])
    def verify_audit() -> dict[str, Any]:
        ok, broken = audit.verify()
        if not ok:
            raise HTTPException(
                status_code=409,
                detail={"chain_ok": False, "broken_row_ids": broken},
            )
        return {"chain_ok": True, "broken_row_ids": []}

    return app


# Module-level app for `uvicorn cbsrm.api.routes:app`
try:
    app = build_app()
except RuntimeError:
    # FastAPI not installed — that's fine, importer can call build_app later
    app = None
