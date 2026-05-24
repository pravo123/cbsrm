"""Tests for the report-manifest -> audit-chain bridge.

These tests run against an in-memory sqlite + :class:`AuditChain`
constructed directly. They do not exercise the HTTP API surface — the
API integration is covered by ``tests/test_api_crisis_dossiers.py``.

Pinned contract:
  * ``AUDIT_EVENT_KIND == "REPORT_EXPORTED"``.
  * ``manifest_subject`` builds ``report:{id}:{window}:{format}``
    with a ``-`` placeholder for missing window_id, and validates
    that ``report_id`` and ``format`` are non-empty strs.
  * ``stamp_manifest_to_chain`` appends one row, returns a 6-key
    dict, and leaves the chain in a verifiable state.
  * Two stamps form a linked chain (``row2.prev_hash == row1.hash``).
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from cbsrm.audit.chain import AuditChain
from cbsrm.diagnostics import build_crisis_dossier
from cbsrm.reporting import (
    AUDIT_EVENT_KIND,
    build_report_manifest,
    build_report_payload,
    manifest_subject,
    stamp_manifest_to_chain,
)


# ─── helpers ────────────────────────────────────────────────────────


@pytest.fixture
def chain() -> AuditChain:
    return AuditChain(sqlite3.connect(":memory:"))


def _crisis_manifest(
    window: str = "2008Q4", *, output_format: str = "json",
) -> dict:
    dossier = build_crisis_dossier(window)
    payload = build_report_payload(dossier)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return build_report_manifest(
        report_id="crisis-dossier",
        output_text=text,
        output_format=output_format,
        window_id=window,
        source="api",
        dossier=dossier,
        payload=payload,
    )


# ─── AUDIT_EVENT_KIND constant ─────────────────────────────────────


def test_audit_event_kind_is_report_exported():
    assert AUDIT_EVENT_KIND == "REPORT_EXPORTED"


# ─── manifest_subject ──────────────────────────────────────────────


def test_manifest_subject_for_full_manifest():
    m = _crisis_manifest("2008Q4")
    assert manifest_subject(m) == "report:crisis-dossier:2008Q4:json"


def test_manifest_subject_dash_when_window_id_missing():
    m = _crisis_manifest("2008Q4")
    m_no_window = dict(m)
    m_no_window["window_id"] = None
    assert (
        manifest_subject(m_no_window)
        == "report:crisis-dossier:-:json"
    )


def test_manifest_subject_dash_when_window_id_empty_string():
    m = _crisis_manifest("2008Q4")
    m_no_window = dict(m)
    m_no_window["window_id"] = ""
    assert (
        manifest_subject(m_no_window)
        == "report:crisis-dossier:-:json"
    )


def test_manifest_subject_propagates_format():
    m = _crisis_manifest("2020Q1", output_format="markdown")
    assert (
        manifest_subject(m)
        == "report:crisis-dossier:2020Q1:markdown"
    )


def test_manifest_subject_rejects_missing_report_id():
    m = _crisis_manifest("2008Q4")
    m_bad = dict(m)
    m_bad["report_id"] = ""
    with pytest.raises(ValueError):
        manifest_subject(m_bad)


def test_manifest_subject_rejects_missing_format():
    m = _crisis_manifest("2008Q4")
    m_bad = dict(m)
    m_bad["format"] = ""
    with pytest.raises(ValueError):
        manifest_subject(m_bad)


# ─── stamp_manifest_to_chain ───────────────────────────────────────


def test_stamp_returns_expected_keys(chain):
    row = stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    assert set(row.keys()) == {
        "row_id", "hash", "prev_hash", "ts",
        "subject", "kind",
    }


def test_stamp_row_exists_in_sqlite(chain):
    row = stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    db_row = chain.conn.execute(
        "SELECT id, kind, subject FROM cbsrm_audit_log WHERE id = ?",
        (row["row_id"],),
    ).fetchone()
    assert db_row is not None
    assert db_row[0] == row["row_id"]


def test_stamp_row_kind_is_report_exported(chain):
    row = stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    assert row["kind"] == "REPORT_EXPORTED"


def test_stamp_row_subject_matches_manifest_subject(chain):
    m = _crisis_manifest("2020Q1", output_format="markdown")
    row = stamp_manifest_to_chain(chain, m)
    assert row["subject"] == manifest_subject(m)
    assert row["subject"] == "report:crisis-dossier:2020Q1:markdown"


def test_stamp_row_payload_round_trips_to_original_manifest(chain):
    m = _crisis_manifest("2023Q1")
    row = stamp_manifest_to_chain(chain, m)
    payload_json = chain.conn.execute(
        "SELECT payload_json FROM cbsrm_audit_log WHERE id = ?",
        (row["row_id"],),
    ).fetchone()[0]
    decoded = json.loads(payload_json)
    # The audit chain serialises with sort_keys=True by design; the
    # decoded structure is therefore key-permuted but value-equal.
    assert decoded == m


def test_stamp_two_events_link_via_prev_hash(chain):
    row1 = stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    row2 = stamp_manifest_to_chain(chain, _crisis_manifest("2020Q1"))
    assert row1["prev_hash"] is None  # first event in the chain
    assert row2["prev_hash"] == row1["hash"]
    assert row2["hash"] != row1["hash"]


def test_chain_verify_passes_after_multiple_stamps(chain):
    stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    stamp_manifest_to_chain(chain, _crisis_manifest("2020Q1"))
    stamp_manifest_to_chain(chain, _crisis_manifest("2023Q1"))
    ok, broken = chain.verify()
    assert ok is True
    assert broken == []


def test_stamp_rejects_non_audit_chain():
    """Defensive type check — passing a bare sqlite Connection is a
    bug at the call-site (the caller should wrap it in AuditChain
    first)."""
    raw_conn = sqlite3.connect(":memory:")
    with pytest.raises(TypeError):
        stamp_manifest_to_chain(
            raw_conn, _crisis_manifest("2008Q4"),  # type: ignore[arg-type]
        )


def test_stamp_ts_is_iso8601_like_string(chain):
    """The chain stamps each row with a UTC ISO-8601 timestamp.
    We do not pin the exact value (wall-clock), just the shape."""
    row = stamp_manifest_to_chain(chain, _crisis_manifest("2008Q4"))
    assert isinstance(row["ts"], str)
    # ISO-8601 begins with YYYY-MM-DDT and includes a 'T' separator.
    assert "T" in row["ts"]
    assert row["ts"][:4].isdigit()


def test_audit_subject_queryable_via_chain_query_subject(chain):
    """Rows written via stamp_manifest_to_chain are visible to the
    existing :meth:`AuditChain.query_subject` API — proves the
    bridge integrates with the existing read surface."""
    m = _crisis_manifest("2008Q4")
    stamp_manifest_to_chain(chain, m)
    subject = manifest_subject(m)
    rows = chain.query_subject(subject, limit=10)
    assert len(rows) == 1
    assert rows[0].kind == "REPORT_EXPORTED"
    assert rows[0].subject == subject
