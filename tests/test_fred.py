"""Tests for cbsrm.data.fred. HTTP-mocked — no live FRED calls."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cbsrm.data.fred import (
    FREDClient, FREDSeriesMeta, FRED_API_BASE,
)


def _fake_observations(values: list[tuple[str, float | None]]) -> dict:
    return {
        "observations": [
            {"date": d, "value": "." if v is None else str(v)}
            for d, v in values
        ]
    }


def _fake_series_meta() -> dict:
    return {
        "seriess": [{
            "id": "SOFR", "title": "Secured Overnight Financing Rate",
            "units": "Percent", "frequency_short": "D",
            "seasonal_adjustment_short": "NSA",
            "observation_start": "2018-04-03",
            "observation_end": "2026-05-19",
            "last_updated": "2026-05-19 09:00:00-05",
            "notes": "Daily rate.",
        }]
    }


@pytest.fixture
def fake_session():
    s = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    s.get = MagicMock(return_value=resp)
    return s, resp


@pytest.fixture
def fred(tmp_path, fake_session):
    sess, _resp = fake_session
    return FREDClient(api_key="testkey", cache_dir=tmp_path / "cache",
                      session=sess)


# ─── Construction ─────────────────────────────────────────────────────


def test_uses_api_key_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FRED_API_KEY", "envkey")
    c = FREDClient(cache_dir=tmp_path / "cache")
    assert c.api_key == "envkey"


def test_explicit_api_key_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("FRED_API_KEY", "envkey")
    c = FREDClient(api_key="passedkey", cache_dir=tmp_path / "cache")
    assert c.api_key == "passedkey"


def test_creates_cache_dir(tmp_path):
    cache = tmp_path / "x" / "y"
    FREDClient(api_key="k", cache_dir=cache)
    assert cache.exists()


def test_cache_none_does_not_create_dir(tmp_path):
    FREDClient(api_key="k", cache_dir=None)
    # No raise — and no cache dir behavior


# ─── series_meta ──────────────────────────────────────────────────────


def test_series_meta_parses_response(fred, fake_session):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value=_fake_series_meta())
    meta = fred.series_meta("SOFR")
    assert isinstance(meta, FREDSeriesMeta)
    assert meta.series_id == "SOFR"
    assert meta.units == "Percent"
    assert meta.frequency == "D"


def test_series_meta_cached_on_second_call(fred, fake_session, tmp_path):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value=_fake_series_meta())
    fred.series_meta("SOFR")
    fred.series_meta("SOFR")
    # session.get should only have been called once thanks to cache
    assert _sess.get.call_count == 1


# ─── get_series ───────────────────────────────────────────────────────


def test_get_series_parses_observations(fred, fake_session):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value=_fake_observations([
        ("2026-05-15", 4.31),
        ("2026-05-16", 4.32),
        ("2026-05-17", None),         # missing — should be filtered
        ("2026-05-19", 4.33),
    ]))
    s = fred.get_series("SOFR")
    assert isinstance(s, pd.Series)
    assert s.name == "SOFR"
    assert len(s) == 3
    assert s.index.tz is not None
    assert float(s.iloc[-1]) == 4.33


def test_get_series_empty_when_no_observations(fred, fake_session):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value={"observations": []})
    s = fred.get_series("SOFR")
    assert s.empty


def test_get_series_all_missing_returns_empty(fred, fake_session):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value=_fake_observations([
        ("2026-05-15", None), ("2026-05-16", None),
    ]))
    s = fred.get_series("SOFR")
    assert s.empty


def test_get_series_param_passthrough(fred, fake_session):
    _sess, resp = fake_session
    resp.json = MagicMock(return_value=_fake_observations([("2026-05-19", 1.0)]))
    fred.get_series("SOFR", observation_start="2020-01-01",
                    observation_end="2025-12-31", frequency="m")
    call = _sess.get.call_args
    params = call.kwargs.get("params", call.args[1] if len(call.args) > 1 else {})
    assert params["series_id"] == "SOFR"
    assert params["observation_start"] == "2020-01-01"
    assert params["observation_end"] == "2025-12-31"
    assert params["frequency"] == "m"


# ─── get_multi ────────────────────────────────────────────────────────


def test_get_multi_aligns_series(fred, fake_session):
    _sess, resp = fake_session
    # Each call returns different obs; rotate through them
    obs_a = _fake_observations([("2026-05-15", 1.0), ("2026-05-16", 1.1)])
    obs_b = _fake_observations([("2026-05-15", 2.0), ("2026-05-17", 2.1)])
    resp.json = MagicMock(side_effect=[obs_a, obs_b])
    df = fred.get_multi(["A", "B"])
    assert set(df.columns) == {"A", "B"}
    # Outer join — should include all dates
    assert len(df) == 3
    assert pd.notna(df["A"].iloc[0])
    assert pd.isna(df["B"].iloc[1])  # 2026-05-16 only in A


def test_get_multi_handles_individual_failure(fred, fake_session):
    _sess, resp = fake_session
    # First call ok, second raises
    obs = _fake_observations([("2026-05-15", 1.0)])

    def side_effect(*args, **kwargs):
        if _sess.get.call_count == 1:
            return resp
        raise RuntimeError("boom")
    _sess.get.side_effect = side_effect
    resp.json = MagicMock(return_value=obs)
    df = fred.get_multi(["A", "B"])
    assert "A" in df.columns
    assert "B" in df.columns
    assert df["B"].dropna().empty


# ─── Retry behavior ───────────────────────────────────────────────────


def test_retries_on_transient_error(tmp_path):
    sess = MagicMock()
    bad = MagicMock(); bad.status_code = 500
    bad.raise_for_status = MagicMock(side_effect=Exception("500"))
    good = MagicMock(); good.status_code = 200
    good.json = MagicMock(return_value=_fake_observations([("2026-05-19", 1.0)]))
    good.raise_for_status = MagicMock()
    sess.get.side_effect = [bad, bad, good]
    c = FREDClient(api_key="k", cache_dir=tmp_path / "c", session=sess,
                   retry_max=3, timeout_s=1.0)
    s = c.get_series("X")
    assert len(s) == 1
    assert sess.get.call_count == 3
