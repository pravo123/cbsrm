"""Tests for cbsrm.diagnostics.replication."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.diagnostics import CRISIS_WINDOWS, replicate, crisis_windows


def _two_correlated_series(n=300, corr=0.95, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="D", tz="UTC")
    base = rng.normal(0.0, 1.0, n).cumsum()
    noise = rng.normal(0.0, 1.0, n)
    # Mix at level not returns to get a smooth correlated pair
    a = pd.Series(base, index=idx, name="a")
    b = pd.Series(corr * base + np.sqrt(1 - corr**2) * noise.cumsum() * 0.1,
                  index=idx, name="b")
    return a, b


# ─── Crisis window dictionary ────────────────────────────────────────


def test_crisis_windows_includes_canonical_episodes():
    w = crisis_windows()
    assert "2008-gfc-acute" in w
    assert "2020-covid" in w
    assert "2023-svb" in w


def test_crisis_windows_well_formed():
    for name, (s, e) in CRISIS_WINDOWS.items():
        ts = pd.Timestamp(s); te = pd.Timestamp(e)
        assert ts < te, f"{name}: start {s} >= end {e}"


# ─── Replicate happy path ────────────────────────────────────────────


def test_replicate_returns_report():
    a, b = _two_correlated_series()
    rep = replicate(a, b, cbsrm_label="A", canonical_label="B")
    assert rep.cbsrm_label == "A"
    assert rep.canonical_label == "B"
    assert rep.full_sample is not None
    assert rep.full_sample.n_overlap > 0


def test_replicate_high_correlation_detected():
    a, b = _two_correlated_series(corr=0.99)
    rep = replicate(a, b)
    assert rep.full_sample.pearson_r > 0.85
    assert rep.full_sample.spearman_rho > 0.85


def test_replicate_low_correlation_detected():
    a, b = _two_correlated_series(corr=0.05)
    rep = replicate(a, b)
    assert rep.full_sample.pearson_r < 0.5


def test_replicate_breaks_out_crisis_windows():
    n = 2000   # ~5+ years
    a, b = _two_correlated_series(n=n)
    rep = replicate(a, b)
    # At least one crisis window in the date range
    assert "2020-covid" in rep.by_window
    cov = rep.by_window["2020-covid"]
    assert cov.n_overlap > 0


def test_replicate_omits_windows_with_no_overlap():
    """If the data doesn't span a window, it shouldn't appear in by_window."""
    idx = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    a = pd.Series(np.arange(100.0), index=idx, name="a")
    b = pd.Series(np.arange(100.0), index=idx, name="b")
    rep = replicate(a, b)
    # 2008 GFC window is outside this date range
    assert "2008-gfc-acute" not in rep.by_window


def test_replicate_handles_empty_series():
    a = pd.Series([], dtype=float, name="a",
                  index=pd.DatetimeIndex([], tz="UTC"))
    b = pd.Series([], dtype=float, name="b",
                  index=pd.DatetimeIndex([], tz="UTC"))
    rep = replicate(a, b)
    assert rep.full_sample is None
    assert any("empty" in w for w in rep.warnings)


def test_replicate_handles_no_overlap():
    """Series in non-overlapping date ranges."""
    a_idx = pd.date_range("2010-01-01", periods=100, freq="D", tz="UTC")
    b_idx = pd.date_range("2020-01-01", periods=100, freq="D", tz="UTC")
    a = pd.Series(np.arange(100.0), index=a_idx, name="a")
    b = pd.Series(np.arange(100.0), index=b_idx, name="b")
    rep = replicate(a, b)
    # full_sample exists but with no rows (or very small)
    if rep.full_sample is not None:
        assert rep.full_sample.n_overlap == 0


def test_replicate_handles_naive_index():
    """If user passes a tz-naive index, it should be coerced to UTC."""
    idx = pd.date_range("2020-01-01", periods=100, freq="D")  # no tz
    a = pd.Series(np.arange(100.0), index=idx, name="a")
    b = pd.Series(np.arange(100.0), index=idx, name="b")
    rep = replicate(a, b)
    assert rep.full_sample is not None
    assert rep.full_sample.pearson_r == pytest.approx(1.0)


# ─── Threshold checks ────────────────────────────────────────────────


def test_meets_threshold_passes_for_high_corr():
    a, b = _two_correlated_series(corr=0.98)
    rep = replicate(a, b)
    ok, breaches = rep.meets_threshold(full_sample_r=0.85, crisis_r=0.80)
    assert ok is True
    assert breaches == []


def test_meets_threshold_fails_for_low_corr():
    a, b = _two_correlated_series(corr=0.0)
    rep = replicate(a, b)
    ok, breaches = rep.meets_threshold(full_sample_r=0.85, crisis_r=0.80)
    assert ok is False
    assert any("full-sample" in b for b in breaches)


# ─── Summary formatting ──────────────────────────────────────────────


def test_summary_renders_human_readable():
    a, b = _two_correlated_series()
    rep = replicate(a, b, cbsrm_label="MyCISS", canonical_label="OFR")
    s = rep.summary()
    assert "MyCISS" in s
    assert "OFR" in s
    assert "Full sample" in s


def test_as_dict_serializable():
    import json
    a, b = _two_correlated_series()
    rep = replicate(a, b)
    d = rep.as_dict()
    s = json.dumps(d, default=str)
    assert "full_sample" in s
