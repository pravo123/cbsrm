"""Tests for cbsrm.diagnostics.crisis_replay."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from cbsrm.diagnostics import (
    CRISIS_WINDOWS, CrisisReplay, CrisisReplayReport,
    replay_all_windows, replay_to_markdown_dossier,
)


# ─── Helpers ──────────────────────────────────────────────────────────


def _flat_series(n=400, level=0.1, freq="D"):
    idx = pd.date_range("2018-01-01", periods=n, freq=freq, tz="UTC")
    return pd.Series([level] * n, index=idx, name="flat")


def _spike_series(spike_start: str, spike_end: str, n: int = 1000,
                  baseline: float = 0.1, peak: float = 0.8,
                  freq: str = "D") -> pd.Series:
    """Synthetic stress series: flat baseline with a Gaussian bump inside a window."""
    idx = pd.date_range("2018-01-01", periods=n, freq=freq, tz="UTC")
    vals = np.full(n, baseline)
    ss = pd.Timestamp(spike_start, tz="UTC")
    se = pd.Timestamp(spike_end, tz="UTC")
    if ss in idx and se in idx:
        in_window = (idx >= ss) & (idx <= se)
        n_in = int(in_window.sum())
        if n_in > 0:
            xs = np.linspace(-2, 2, n_in)
            bump = (peak - baseline) * np.exp(-(xs ** 2))
            vals[in_window] = baseline + bump
    return pd.Series(vals, index=idx, name="stress")


# ─── Construction ─────────────────────────────────────────────────────


def test_rejects_empty_series():
    with pytest.raises(ValueError, match="non-empty"):
        CrisisReplay(values=pd.Series(dtype=float))


def test_accepts_naive_index_and_localizes():
    """Naive index → UTC localization."""
    idx = pd.date_range("2020-01-01", periods=50, freq="D")
    s = pd.Series(np.arange(50.0), index=idx, name="x")
    rp = CrisisReplay(s)
    assert rp.values.index.tz is not None


def test_indicator_id_default():
    rp = CrisisReplay(_flat_series())
    assert rp.indicator_id == "indicator"


# ─── replay (canonical windows) ──────────────────────────────────────


def test_replay_unknown_window_raises():
    rp = CrisisReplay(_flat_series())
    with pytest.raises(KeyError, match="unknown window"):
        rp.replay("not-a-real-crisis")


def test_replay_no_observations_returns_empty_report():
    """Indicator that doesn't span the 2008 window."""
    idx = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    s = pd.Series(np.arange(100.0), index=idx, name="x")
    rp = CrisisReplay(s, indicator_id="X")
    r = rp.replay("2008-gfc-acute")
    assert r.n_obs == 0
    assert r.peak_value is None
    assert any("no observations" in w for w in r.warnings)


def test_replay_finds_peak_inside_window():
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.9)
    rp = CrisisReplay(s, indicator_id="STRESS")
    r = rp.replay("2020-covid")
    assert r.peak_value > 0.85
    assert r.window_start <= r.peak_date <= r.window_end


def test_replay_computes_z_score_when_pre_window_has_variance():
    """Make a pre-crisis with non-zero std so z is computable."""
    n = 1000
    idx = pd.date_range("2018-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.default_rng(7)
    vals = 0.1 + rng.normal(0.0, 0.02, n)   # small noise around 0.1
    # Add a spike in 2020-covid window
    covid_start = pd.Timestamp("2020-02-15", tz="UTC")
    covid_end = pd.Timestamp("2020-05-15", tz="UTC")
    in_covid = (idx >= covid_start) & (idx <= covid_end)
    vals[in_covid] = 0.8
    s = pd.Series(vals, index=idx, name="x")
    rp = CrisisReplay(s, indicator_id="STRESS")
    r = rp.replay("2020-covid")
    assert r.z_peak is not None
    assert r.z_peak > 5.0   # 0.8 is ~35 stdevs above 0.1+/-0.02


def test_replay_amplification_is_peak_over_baseline():
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.5)
    rp = CrisisReplay(s, indicator_id="STRESS")
    r = rp.replay("2020-covid")
    assert r.amplification is not None
    # peak ≈ 0.5, baseline ≈ 0.1 → amp ≈ 5
    assert 4.0 < r.amplification < 6.0


def test_replay_days_to_peak_nonnegative():
    s = _spike_series("2020-03-15", "2020-04-15")
    rp = CrisisReplay(s)
    r = rp.replay("2020-covid")
    assert r.days_to_peak >= 0


def test_replay_post_window_recovery_computed():
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.9)
    rp = CrisisReplay(s)
    r = rp.replay("2020-covid")
    assert r.recovery_value is not None
    # Post-window should be ~ baseline
    assert abs(r.recovery_value - 0.1) < 0.05


# ─── Subindex attribution ────────────────────────────────────────────


def test_replay_attribution_from_subindex_frame():
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.9)
    # Build a subindex DataFrame with one row per date
    sub = pd.DataFrame({
        "credit":           s * 0.4,
        "funding":          s * 0.3,
        "equity":           s * 0.2,
        "vol":              s * 0.1,
    }, index=s.index)
    rp = CrisisReplay(s, subindex_values=sub, indicator_id="X")
    r = rp.replay("2020-covid")
    assert set(r.attribution.keys()) == {"credit", "funding", "equity", "vol"}
    # Credit (highest weight) should dominate at peak
    assert r.attribution["credit"] > r.attribution["vol"]


def test_replay_attribution_handles_missing_peak_date():
    """If subindex frame doesn't include the exact peak date, fall back to nearest."""
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.9, freq="D")
    # Subindex with weekly cadence — won't have the exact daily peak
    weekly_idx = pd.date_range(s.index.min(), s.index.max(), freq="W", tz="UTC")
    sub = pd.DataFrame({
        "x": np.linspace(0.1, 0.9, len(weekly_idx)),
    }, index=weekly_idx)
    rp = CrisisReplay(s, subindex_values=sub, indicator_id="X")
    r = rp.replay("2020-covid")
    # Either attribution found (via nearest) or warning logged
    assert "x" in r.attribution or any("nearest" in w for w in r.warnings)


# ─── Multi-window helpers ────────────────────────────────────────────


def test_replay_all_windows_skips_no_overlap():
    """An indicator only spanning 2024 should skip 2008 etc."""
    idx = pd.date_range("2024-01-01", periods=300, freq="D", tz="UTC")
    s = pd.Series(np.arange(300.0), index=idx, name="x")
    rp = CrisisReplay(s)
    out = replay_all_windows(rp)
    # Most pre-2024 windows should be absent
    assert "2008-gfc-acute" not in out
    assert "2020-covid" not in out


def test_replay_all_windows_returns_dict_of_reports():
    s = _spike_series("2020-03-15", "2020-04-15")
    rp = CrisisReplay(s)
    out = replay_all_windows(rp)
    assert "2020-covid" in out
    assert isinstance(out["2020-covid"], CrisisReplayReport)


def test_markdown_dossier_has_summary_and_per_episode():
    s = _spike_series("2020-03-15", "2020-04-15", baseline=0.1, peak=0.9)
    rp = CrisisReplay(s, indicator_id="OFR-FSI")
    md = replay_to_markdown_dossier(rp)
    assert "# Crisis-replay dossier" in md
    assert "OFR-FSI" in md
    assert "2020-covid" in md
    # Per-episode section
    assert "## 2020-covid" in md


# ─── Serialization ───────────────────────────────────────────────────


def test_as_dict_round_trips_through_json():
    s = _spike_series("2020-03-15", "2020-04-15")
    rp = CrisisReplay(s, indicator_id="X")
    r = rp.replay("2020-covid")
    d = r.as_dict()
    js = json.dumps(d, default=str)
    back = json.loads(js)
    assert back["indicator_id"] == "X"
    assert back["window_name"] == "2020-covid"


def test_to_text_non_empty_for_real_episode():
    s = _spike_series("2020-03-15", "2020-04-15")
    rp = CrisisReplay(s, indicator_id="X")
    text = rp.replay("2020-covid").to_text()
    assert "2020-covid" in text
    assert "peak" in text.lower()


def test_to_text_handles_empty_window():
    """Should not crash when there's no overlap."""
    idx = pd.date_range("2025-01-01", periods=30, freq="D", tz="UTC")
    s = pd.Series(np.arange(30.0), index=idx, name="x")
    text = CrisisReplay(s).replay("2008-gfc-acute").to_text()
    assert "insufficient" in text.lower()


def test_to_markdown_handles_empty_window():
    idx = pd.date_range("2025-01-01", periods=30, freq="D", tz="UTC")
    s = pd.Series(np.arange(30.0), index=idx, name="x")
    md = CrisisReplay(s).replay("2008-gfc-acute").to_markdown()
    assert "Insufficient" in md


# ─── Pre-window guard ───────────────────────────────────────────────


def test_no_pre_window_data_is_warned_not_failed():
    """If indicator starts AT the window, no pre-window observations available."""
    # Start exactly at COVID window start
    idx = pd.date_range("2020-02-15", periods=300, freq="D", tz="UTC")
    s = pd.Series(np.linspace(0.1, 0.9, 300), index=idx, name="x")
    rp = CrisisReplay(s, indicator_id="X")
    r = rp.replay("2020-covid")
    # No pre-window data → baseline_pre is None, z_peak None
    assert r.baseline_pre is None
    assert r.z_peak is None
    assert any("no pre-window" in w for w in r.warnings)
    # Peak is still computed
    assert r.peak_value is not None
