"""Tests for cbsrm.audit.audited_indicator.AuditedIndicator."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from cbsrm.audit import AuditChain, AuditedIndicator
from cbsrm.audit.chain import AuditEventKind
from cbsrm.indicators import STLFSIWrap
from cbsrm.indicators.base import IndicatorResult


@pytest.fixture
def conn():
    return sqlite3.connect(":memory:")


@pytest.fixture
def audit(conn):
    return AuditChain(conn)


def _stlfsi_df(n: int = 10):
    return pd.DataFrame(
        {"STLFSI4": np.linspace(-1.0, 2.0, n)},
        index=pd.date_range("2020-01-01", periods=n, freq="W"),
    )


# ─── Construction ─────────────────────────────────────────────────────


def test_wraps_real_indicator(audit):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    assert ai.id == "STLFSI4"
    assert ai.version == "1.0.0"
    assert "St. Louis Fed" in ai.source


def test_required_series_delegates(audit):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    assert ai.required_series() == ["STLFSI4"]


def test_rejects_object_missing_protocol_methods(audit):
    class Bogus: pass
    with pytest.raises(TypeError, match="IIndicator"):
        AuditedIndicator(Bogus(), audit)


# ─── Happy-path lifecycle ─────────────────────────────────────────────


def test_compute_writes_full_lifecycle(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit, consumer="test")
    result = ai.compute(_stlfsi_df())

    kinds = [r[0] for r in conn.execute(
        "SELECT kind FROM cbsrm_audit_log ORDER BY id"
    ).fetchall()]
    assert kinds == [
        AuditEventKind.REQUESTED.value,
        AuditEventKind.INPUT_FETCHED.value,
        AuditEventKind.COMPUTED.value,
        AuditEventKind.SERVED.value,
    ]


def test_result_carries_audit_row_id(audit):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    result = ai.compute(_stlfsi_df())
    assert isinstance(result, IndicatorResult)
    assert result.audit_row_id is not None
    assert result.audit_row_id > 0


def test_chain_remains_verifiable_after_compute(audit):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    ai.compute(_stlfsi_df())
    ai.compute(_stlfsi_df(n=20))
    ok, broken = audit.verify()
    assert ok is True
    assert broken == []


def test_subject_matches_indicator_id(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    ai.compute(_stlfsi_df())
    subjects = [r[0] for r in conn.execute(
        "SELECT subject FROM cbsrm_audit_log"
    ).fetchall()]
    assert all(s == "STLFSI4" for s in subjects)


def test_consumer_recorded_in_served_payload(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit, consumer="dashboard_v2")
    ai.compute(_stlfsi_df())
    served = conn.execute(
        "SELECT payload_json FROM cbsrm_audit_log WHERE kind = 'SERVED'"
    ).fetchone()
    assert served is not None
    import json
    payload = json.loads(served[0])
    assert payload["consumer"] == "dashboard_v2"


def test_input_metadata_recorded(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    ai.compute(_stlfsi_df(n=12))
    fetched = conn.execute(
        "SELECT payload_json FROM cbsrm_audit_log WHERE kind = 'INPUT_FETCHED'"
    ).fetchone()
    import json
    payload = json.loads(fetched[0])
    assert payload["n_rows"] == 12
    assert "STLFSI4" in payload["columns"]


# ─── Failure paths ────────────────────────────────────────────────────


def test_empty_dataframe_writes_input_missing(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    with pytest.raises(ValueError, match="empty"):
        ai.compute(pd.DataFrame())
    kinds = [r[0] for r in conn.execute(
        "SELECT kind FROM cbsrm_audit_log ORDER BY id"
    ).fetchall()]
    assert kinds == [
        AuditEventKind.REQUESTED.value,
        AuditEventKind.INPUT_MISSING.value,
    ]


def test_compute_failure_writes_failed_event(audit, conn):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    # STLFSIWrap requires the STLFSI4 column; pass wrong one
    bad = pd.DataFrame({"WRONG": [1.0, 2.0]},
                       index=pd.date_range("2020-01-01", periods=2, freq="W"))
    with pytest.raises(ValueError):
        ai.compute(bad)

    kinds = [r[0] for r in conn.execute(
        "SELECT kind FROM cbsrm_audit_log ORDER BY id"
    ).fetchall()]
    assert AuditEventKind.FAILED.value in kinds


def test_failed_chain_still_verifiable(audit):
    ai = AuditedIndicator(STLFSIWrap(), audit)
    bad = pd.DataFrame({"WRONG": [1.0]},
                       index=pd.date_range("2020-01-01", periods=1, freq="W"))
    with pytest.raises(ValueError):
        ai.compute(bad)
    ok, broken = audit.verify()
    assert ok is True
    assert broken == []
