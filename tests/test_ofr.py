"""Tests for cbsrm.data.ofr.OFRClient — HTTP-mocked, no live calls."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cbsrm.data.ofr import OFRClient, OFRFSIMeta


_FSI_CSV = """\
Date,OFR FSI,Credit,Equity valuation,Funding,Safe assets,Volatility
2020-02-15,-0.5,0.1,-0.2,-0.1,-0.1,-0.2
2020-03-01,1.2,0.3,0.4,0.3,0.1,0.1
2020-03-15,3.4,0.8,0.9,0.7,0.5,0.5
2020-04-01,2.1,0.5,0.6,0.4,0.3,0.3
"""


@pytest.fixture
def fake_session():
    s = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.text = _FSI_CSV
    s.get = MagicMock(return_value=resp)
    return s, resp


@pytest.fixture
def client(tmp_path, fake_session):
    sess, _ = fake_session
    return OFRClient(cache_dir=tmp_path / "ofr", session=sess)


# ─── Schema + init ────────────────────────────────────────────────────


def test_default_csv_url_used_when_no_env(monkeypatch, tmp_path):
    monkeypatch.delenv("OFR_FSI_CSV_URL", raising=False)
    c = OFRClient(cache_dir=tmp_path / "ofr")
    assert "financialresearch.gov" in c.csv_url


def test_env_url_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OFR_FSI_CSV_URL", "https://example.org/x.csv")
    c = OFRClient(cache_dir=tmp_path / "ofr")
    assert c.csv_url == "https://example.org/x.csv"


def test_constructor_url_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("OFR_FSI_CSV_URL", "https://envvar.org/x.csv")
    c = OFRClient(csv_url="https://explicit.org/x.csv",
                  cache_dir=tmp_path / "ofr")
    assert c.csv_url == "https://explicit.org/x.csv"


def test_source_info_returns_metadata(client):
    meta = client.source_info()
    assert isinstance(meta, OFRFSIMeta)
    assert "Treasury" in meta.source
    assert meta.frequency == "D"


# ─── get_fsi ──────────────────────────────────────────────────────────


def test_get_fsi_returns_dataframe(client):
    df = client.get_fsi()
    assert isinstance(df, pd.DataFrame)
    assert "OFR FSI" in df.columns
    assert "Credit" in df.columns


def test_get_fsi_dates_parsed_utc(client):
    df = client.get_fsi()
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"


def test_get_fsi_values_are_floats(client):
    df = client.get_fsi()
    for col in df.columns:
        assert df[col].dtype.kind == "f"


def test_get_fsi_sorted_ascending(client):
    df = client.get_fsi()
    assert df.index.is_monotonic_increasing


def test_get_fsi_cached_on_second_call(fake_session, tmp_path):
    sess, _ = fake_session
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess)
    c.get_fsi()
    c.get_fsi()
    assert sess.get.call_count == 1   # second call hits cache


def test_get_fsi_handles_lowercase_date_column(tmp_path, fake_session):
    sess, resp = fake_session
    resp.text = "date,OFR FSI\n2024-01-01,0.5\n2024-01-02,0.7\n"
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess)
    df = c.get_fsi()
    assert len(df) == 2
    assert df["OFR FSI"].iloc[-1] == 0.7


def test_get_fsi_handles_missing_date_col_fallback(tmp_path, fake_session):
    sess, resp = fake_session
    # No 'date' or 'Date' column — first column treated as date
    resp.text = "ObservationDate,OFR FSI\n2024-01-01,0.5\n2024-01-02,0.7\n"
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess)
    df = c.get_fsi()
    assert len(df) == 2


# ─── Retry behavior ───────────────────────────────────────────────────


def test_get_fsi_retries_on_transient(tmp_path):
    sess = MagicMock()
    bad = MagicMock(); bad.status_code = 503
    bad.raise_for_status = MagicMock(side_effect=Exception("503"))
    good = MagicMock(); good.status_code = 200
    good.text = _FSI_CSV
    good.raise_for_status = MagicMock()
    sess.get.side_effect = [bad, good]
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess,
                  retry_max=3, timeout_s=1.0)
    df = c.get_fsi()
    assert len(df) == 4
    assert sess.get.call_count == 2


def test_get_fsi_raises_after_max_retries(tmp_path):
    sess = MagicMock()
    bad = MagicMock(); bad.status_code = 503
    bad.raise_for_status = MagicMock(side_effect=Exception("503"))
    sess.get.return_value = bad
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess,
                  retry_max=2, timeout_s=0.1)
    with pytest.raises(RuntimeError, match="failed"):
        c.get_fsi()


# ─── STFM API ─────────────────────────────────────────────────────────


def test_get_stfm_series_parses_data_envelope(tmp_path):
    sess = MagicMock()
    resp = MagicMock(); resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "data": [
            {"date": "2024-05-01", "value": 4.31},
            {"date": "2024-05-02", "value": 4.32},
        ]
    })
    sess.get.return_value = resp
    c = OFRClient(cache_dir=tmp_path / "ofr", session=sess)
    s = c.get_stfm_series("SOFR")
    assert isinstance(s, pd.Series)
    assert len(s) == 2
    assert s.iloc[-1] == 4.32
