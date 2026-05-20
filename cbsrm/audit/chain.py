"""
Tamper-evident audit chain for systemic-risk computations.
==========================================================

Every value computed by a CBSRM indicator is appended as one row in
`cbsrm_audit_log`. Each row carries a sha256 hash of (prev_hash || ts ||
kind || subject || payload_json). Replaying the chain top-to-bottom and
re-hashing must match the stored hash on every row; otherwise the chain
is broken (tampered, partial write, schema migration mishap).

This is the same chain design used in production at WaverVanir for
broker order audit (5-state lifecycle: SUBMITTED → ROUTED → ACKED →
FILLED → SETTLED + REJECTED/CANCELED), ported and generalized for
methodology audit.

For CBSRM the canonical lifecycle is:
  REQUESTED → INPUT_FETCHED → COMPUTED → SERVED

Each indicator's compute call writes one row per stage, so consumers
can later prove: (a) which input vintage was used, (b) which methodology
version produced the value, and (c) that no row between request and
serve was modified.

Storage
-------

The chain persists to SQLite by default; pass any sqlite3.Connection
or a class with a .conn attribute. For production deploys swap to
Postgres or any append-only ledger by subclassing _persist().
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

log = logging.getLogger("cbsrm.audit.chain")


class AuditEventKind(str, Enum):
    """Canonical event kinds in a CBSRM computation lifecycle."""
    REQUESTED       = "REQUESTED"
    INPUT_FETCHED   = "INPUT_FETCHED"
    INPUT_MISSING   = "INPUT_MISSING"
    COMPUTED        = "COMPUTED"
    SERVED          = "SERVED"
    METHOD_UPGRADED = "METHOD_UPGRADED"
    REPRODUCED      = "REPRODUCED"
    FAILED          = "FAILED"


HAPPY_PATH = (
    AuditEventKind.REQUESTED,
    AuditEventKind.INPUT_FETCHED,
    AuditEventKind.COMPUTED,
    AuditEventKind.SERVED,
)


@dataclass
class AuditEvent:
    """One audited event."""
    kind: AuditEventKind
    subject: str            # 'CISS-US', 'SRISK', etc.
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditRow:
    id: int
    ts: str
    kind: str
    subject: str
    payload: dict[str, Any]
    hash: str
    prev_hash: str | None


class AuditChain:
    """sha256-chained append-only audit log.

    Pass either a sqlite3.Connection directly or any object with a `.conn`
    attribute. For in-memory use pass sqlite3.connect(":memory:").
    """

    def __init__(self, conn_or_holder: Any) -> None:
        if hasattr(conn_or_holder, "conn"):
            self.conn: sqlite3.Connection = conn_or_holder.conn
        else:
            self.conn = conn_or_holder
        self._ensure_schema()
        self._last_hash = self._load_last_hash()

    def _ensure_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cbsrm_audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT NOT NULL,
                kind         TEXT NOT NULL,
                subject      TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                hash         TEXT NOT NULL,
                prev_hash    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cal_ts      ON cbsrm_audit_log(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_cal_subject ON cbsrm_audit_log(subject);
            CREATE INDEX IF NOT EXISTS idx_cal_kind    ON cbsrm_audit_log(kind);
        """)
        self.conn.commit()

    def _load_last_hash(self) -> str | None:
        row = self.conn.execute(
            "SELECT hash FROM cbsrm_audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _compute_hash(prev_hash: str | None, ts: str, kind: str,
                      subject: str, payload_json: str) -> str:
        h = hashlib.sha256()
        h.update((prev_hash or "").encode("utf-8"))
        h.update(b"\x1e")
        h.update(ts.encode("utf-8"))
        h.update(b"\x1e")
        h.update(kind.encode("utf-8"))
        h.update(b"\x1e")
        h.update(subject.encode("utf-8"))
        h.update(b"\x1e")
        h.update(payload_json.encode("utf-8"))
        return h.hexdigest()

    # ─── Public API ───────────────────────────────────────────────────

    def append(self, event: AuditEvent) -> int:
        """Append one event. Returns row id."""
        ts = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(event.payload, default=str, sort_keys=True)
        prev = self._last_hash
        kind_str = event.kind.value if isinstance(event.kind, AuditEventKind) else str(event.kind)
        h = self._compute_hash(prev, ts, kind_str, event.subject, payload_json)
        cur = self.conn.execute(
            """INSERT INTO cbsrm_audit_log (ts, kind, subject, payload_json, hash, prev_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ts, kind_str, event.subject, payload_json, h, prev),
        )
        self.conn.commit()
        self._last_hash = h
        return cur.lastrowid

    def verify(self, start_id: int = 1) -> tuple[bool, list[int]]:
        """Re-hash rows from start_id and compare. Returns (ok, broken_ids)."""
        rows = self.conn.execute(
            """SELECT id, ts, kind, subject, payload_json, hash, prev_hash
               FROM cbsrm_audit_log WHERE id >= ? ORDER BY id ASC""",
            (start_id,),
        ).fetchall()

        broken: list[int] = []
        prev_actual: str | None = None
        first = True

        for r in rows:
            rid, ts, kind, subject, payload_json, stored_hash, stored_prev = r
            if first:
                if start_id == 1 and stored_prev is not None:
                    broken.append(rid)
                prev_actual = stored_prev
                first = False
            else:
                if stored_prev != prev_actual:
                    broken.append(rid)
            h = self._compute_hash(prev_actual, ts, kind, subject, payload_json)
            if h != stored_hash and rid not in broken:
                broken.append(rid)
            prev_actual = stored_hash

        return (len(broken) == 0, broken)

    def query_subject(self, subject: str, limit: int = 100) -> list[AuditRow]:
        rows = self.conn.execute(
            """SELECT id, ts, kind, subject, payload_json, hash, prev_hash
               FROM cbsrm_audit_log WHERE subject = ?
               ORDER BY id DESC LIMIT ?""",
            (subject, int(limit)),
        ).fetchall()
        return [
            AuditRow(
                id=r[0], ts=r[1], kind=r[2], subject=r[3],
                payload=json.loads(r[4]), hash=r[5], prev_hash=r[6],
            )
            for r in rows
        ]

    def export_for_subject(self, subject: str) -> list[dict[str, Any]]:
        """Full chain for one indicator, ordered earliest-first. Regulator-grade."""
        rows = self.conn.execute(
            """SELECT id, ts, kind, subject, payload_json, hash, prev_hash
               FROM cbsrm_audit_log WHERE subject = ? ORDER BY id ASC""",
            (subject,),
        ).fetchall()
        return [
            {
                "id": r[0], "ts": r[1], "kind": r[2], "subject": r[3],
                "payload": json.loads(r[4]), "hash": r[5], "prev_hash": r[6],
            }
            for r in rows
        ]
