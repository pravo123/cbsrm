"""Tests for cbsrm.audit.chain.AuditChain — tamper-evident audit log."""
from __future__ import annotations

import sqlite3

import pytest

from cbsrm.audit.chain import (
    AuditChain, AuditEvent, AuditEventKind, HAPPY_PATH,
)


@pytest.fixture
def conn():
    return sqlite3.connect(":memory:")


# ─── Schema + init ────────────────────────────────────────────────────


def test_schema_created(conn):
    AuditChain(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cbsrm_audit_log'"
    ).fetchone()
    assert row is not None


def test_init_is_idempotent(conn):
    AuditChain(conn)
    AuditChain(conn)
    AuditChain(conn)


def test_accepts_holder_object_with_conn_attr(conn):
    class Holder:
        pass
    holder = Holder()
    holder.conn = conn
    a = AuditChain(holder)
    a.append(AuditEvent(kind=AuditEventKind.REQUESTED, subject="X"))
    assert a._last_hash is not None


# ─── Append + hash chain ──────────────────────────────────────────────


def test_first_row_has_null_prev_hash(conn):
    a = AuditChain(conn)
    rid = a.append(AuditEvent(kind=AuditEventKind.REQUESTED, subject="CISS-US"))
    assert rid == 1
    row = conn.execute(
        "SELECT prev_hash FROM cbsrm_audit_log WHERE id=1"
    ).fetchone()
    assert row[0] is None


def test_subsequent_rows_chain(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "S"))
    a.append(AuditEvent(AuditEventKind.INPUT_FETCHED, "S", {"n": 100}))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "S", {"val": 0.42}))
    rows = conn.execute(
        "SELECT id, hash, prev_hash FROM cbsrm_audit_log ORDER BY id"
    ).fetchall()
    assert len(rows) == 3
    # row 2's prev = row 1's hash; row 3's prev = row 2's hash
    assert rows[1][2] == rows[0][1]
    assert rows[2][2] == rows[1][1]
    # All hashes distinct
    assert len({rows[0][1], rows[1][1], rows[2][1]}) == 3


def test_last_hash_persists_across_instances(conn):
    a1 = AuditChain(conn)
    a1.append(AuditEvent(AuditEventKind.REQUESTED, "S"))
    a1.append(AuditEvent(AuditEventKind.SERVED, "S"))
    last1 = a1._last_hash

    a2 = AuditChain(conn)
    assert a2._last_hash == last1

    a2.append(AuditEvent(AuditEventKind.REPRODUCED, "S"))
    row = conn.execute(
        "SELECT prev_hash FROM cbsrm_audit_log WHERE id=3"
    ).fetchone()
    assert row[0] == last1


# ─── Verification ─────────────────────────────────────────────────────


def test_clean_chain_verifies(conn):
    a = AuditChain(conn)
    for i in range(10):
        a.append(AuditEvent(AuditEventKind.REQUESTED, f"S{i}", {"i": i}))
    ok, broken = a.verify()
    assert ok is True
    assert broken == []


def test_verify_detects_payload_tamper(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "S", {"x": 1}))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "S", {"v": 0.5}))
    conn.execute("UPDATE cbsrm_audit_log SET payload_json='{\"x\": 999}' WHERE id=1")
    conn.commit()
    ok, broken = a.verify()
    assert ok is False
    assert 1 in broken


def test_verify_detects_hash_swap(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "S"))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "S"))
    conn.execute("UPDATE cbsrm_audit_log SET hash=? WHERE id=1", ("0"*64,))
    conn.commit()
    ok, broken = a.verify()
    assert ok is False
    assert 1 in broken


def test_verify_detects_prev_hash_tamper(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "S"))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "S"))
    conn.execute("UPDATE cbsrm_audit_log SET prev_hash='deadbeef' WHERE id=2")
    conn.commit()
    ok, broken = a.verify()
    assert ok is False
    assert 2 in broken


# ─── Queries ──────────────────────────────────────────────────────────


def test_query_subject_filters(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "A"))
    a.append(AuditEvent(AuditEventKind.REQUESTED, "B"))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "A"))
    rows = a.query_subject("A")
    assert len(rows) == 2
    assert all(r.subject == "A" for r in rows)


def test_export_for_subject_ordered(conn):
    a = AuditChain(conn)
    a.append(AuditEvent(AuditEventKind.REQUESTED, "X"))
    a.append(AuditEvent(AuditEventKind.INPUT_FETCHED, "X", {"n": 10}))
    a.append(AuditEvent(AuditEventKind.COMPUTED, "X", {"val": 0.3}))
    export = a.export_for_subject("X")
    assert [r["kind"] for r in export] == [
        "REQUESTED", "INPUT_FETCHED", "COMPUTED",
    ]


# ─── Constants ────────────────────────────────────────────────────────


def test_happy_path_constants():
    assert len(HAPPY_PATH) == 4
    assert HAPPY_PATH[0] == AuditEventKind.REQUESTED
    assert HAPPY_PATH[-1] == AuditEventKind.SERVED
