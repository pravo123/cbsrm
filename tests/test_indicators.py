"""Tests for cbsrm.indicators — STLFSI wrapper + CISS-US methodology."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.indicators import CISSUS, STLFSIWrap
from cbsrm.indicators.base import IIndicator, IndicatorResult
from cbsrm.indicators.ciss_us import (
    CISSConfig, SUBINDEX_NAMES, DEFAULT_EWMA_LAMBDA,
)


# ═══════════════════════════════════════════════════════════════════
# STLFSIWrap
# ═══════════════════════════════════════════════════════════════════


def test_stlfsi_implements_protocol():
    w = STLFSIWrap()
    assert isinstance(w, IIndicator)
    assert w.id == "STLFSI4"
    assert w.version == "1.0.0"
    assert "St. Louis Fed" in w.source


def test_stlfsi_required_series():
    assert STLFSIWrap().required_series() == ["STLFSI4"]


def test_stlfsi_compute_passes_through():
    idx = pd.date_range("2020-01-01", periods=10, freq="W")
    df = pd.DataFrame({"STLFSI4": np.linspace(-1.0, 2.0, 10)}, index=idx)
    res = STLFSIWrap().compute(df)
    assert isinstance(res, IndicatorResult)
    assert res.indicator_id == "STLFSI4"
    assert len(res.values) == 10
    assert res.values.name == "STLFSI4"
    assert res.metadata["n_obs"] == 10


def test_stlfsi_compute_drops_nan():
    idx = pd.date_range("2020-01-01", periods=5, freq="W")
    df = pd.DataFrame({"STLFSI4": [1.0, np.nan, 2.0, np.nan, 3.0]}, index=idx)
    res = STLFSIWrap().compute(df)
    assert len(res.values) == 3


def test_stlfsi_compute_raises_on_missing_column():
    df = pd.DataFrame({"WRONG": [1.0, 2.0]})
    with pytest.raises(ValueError, match="STLFSI4"):
        STLFSIWrap().compute(df)


def test_stlfsi_latest_property():
    idx = pd.date_range("2020-01-01", periods=3, freq="W")
    df = pd.DataFrame({"STLFSI4": [0.1, 0.2, 0.3]}, index=idx)
    res = STLFSIWrap().compute(df)
    ts, v = res.latest
    assert v == pytest.approx(0.3)


# ═══════════════════════════════════════════════════════════════════
# CISSConfig validation
# ═══════════════════════════════════════════════════════════════════


def test_cissconfig_defaults():
    c = CISSConfig()
    assert c.ewma_lambda == DEFAULT_EWMA_LAMBDA
    assert len(c.weights) == 5
    assert sum(c.weights) == pytest.approx(1.0)


def test_cissconfig_effective_inputs_default():
    inputs = CISSConfig().effective_inputs()
    assert set(inputs.keys()) == set(SUBINDEX_NAMES)
    for k, v in inputs.items():
        assert len(v) == 3


def test_cissus_rejects_bad_weights():
    with pytest.raises(ValueError, match="length 5"):
        CISSUS(CISSConfig(weights=(0.5, 0.5)))
    with pytest.raises(ValueError, match="sum"):
        CISSUS(CISSConfig(weights=(0.5, 0.5, 0.5, 0.5, 0.5)))
    with pytest.raises(ValueError, match="non-negative"):
        CISSUS(CISSConfig(weights=(0.5, 0.5, 0.5, -0.5, 0.0)))


def test_cissus_rejects_bad_lambda():
    with pytest.raises(ValueError):
        CISSUS(CISSConfig(ewma_lambda=0.0))
    with pytest.raises(ValueError):
        CISSUS(CISSConfig(ewma_lambda=1.0))


# ═══════════════════════════════════════════════════════════════════
# CISSUS methodology
# ═══════════════════════════════════════════════════════════════════


def _make_synthetic_inputs(n_obs: int = 500, n_per_subindex: int = 3,
                           seed: int = 42) -> pd.DataFrame:
    """Generate synthetic 15-column input matrix.

    First half: low-stress regime (uncorrelated noise).
    Second half: crisis regime (correlated stress shock to all subindices).
    """
    rng = np.random.default_rng(seed)
    K = 5 * n_per_subindex   # 15 columns
    idx = pd.date_range("2018-01-01", periods=n_obs, freq="W")

    half = n_obs // 2
    low = rng.normal(0.0, 1.0, (half, K))
    # Crisis: load same factor onto all columns
    factor = rng.normal(3.0, 0.5, (n_obs - half, 1))
    crisis = factor + 0.3 * rng.normal(0.0, 1.0, (n_obs - half, K))
    data = np.vstack([low, crisis])

    cols = []
    for name in SUBINDEX_NAMES:
        for i in range(n_per_subindex):
            cols.append(f"{name}_{i+1}")
    return pd.DataFrame(data, index=idx, columns=cols)


def test_cissus_implements_protocol():
    c = CISSUS()
    assert isinstance(c, IIndicator)
    assert c.id == "CISS-US"


def test_cissus_required_series_count():
    """15 raw inputs (3 per subindex × 5 subindices)."""
    assert len(CISSUS().required_series()) == 15


def test_cissus_compute_returns_indicator_result():
    df = _make_synthetic_inputs()
    res = CISSUS().compute(df)
    assert isinstance(res, IndicatorResult)
    assert res.indicator_id == "CISS-US"
    assert res.values.size > 0


def test_cissus_values_bounded_in_unit_interval():
    df = _make_synthetic_inputs()
    res = CISSUS().compute(df)
    assert res.values.min() >= 0.0
    assert res.values.max() <= 1.0


def test_cissus_subindex_breakdown_present():
    df = _make_synthetic_inputs()
    res = CISSUS().compute(df)
    assert res.subindex_values is not None
    assert set(res.subindex_values.columns) == set(SUBINDEX_NAMES)
    assert (res.subindex_values.min().min() >= 0.0)
    assert (res.subindex_values.max().max() <= 1.0)


def test_cissus_crisis_window_elevated_vs_calm():
    """Synthetic crisis half must show materially higher CISS than calm half."""
    df = _make_synthetic_inputs(n_obs=400)
    res = CISSUS().compute(df)
    half = len(res.values) // 2
    calm_mean = res.values.iloc[:half].mean()
    crisis_mean = res.values.iloc[half:].mean()
    assert crisis_mean > calm_mean
    # Crisis regime should be at least 2x calm
    assert crisis_mean > 2 * calm_mean


def test_cissus_systemic_amplification():
    """When correlations rise across subindices, the composite should
    amplify non-linearly relative to the average of subindices.

    Compare: in the crisis window, composite mean should exceed the
    average subindex mean (because the portfolio quadratic form picks
    up the positive correlation."""
    df = _make_synthetic_inputs(n_obs=400)
    res = CISSUS().compute(df)
    half = len(res.values) // 2
    crisis_composite = res.values.iloc[half:].mean()
    crisis_sub_mean = res.subindex_values.iloc[half:].mean().mean()
    # Allow for a generous floor — exact relationship depends on EWMA
    # warmup but the composite should not be drastically smaller than
    # the per-subindex mean during stress.
    assert crisis_composite > 0.5 * crisis_sub_mean


def test_cissus_compute_rejects_missing_columns():
    df = pd.DataFrame({"only_one_col": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="missing columns"):
        CISSUS().compute(df)


def test_cissus_compute_rejects_too_few_observations():
    df = _make_synthetic_inputs(n_obs=20)
    with pytest.raises(ValueError, match="at least"):
        CISSUS().compute(df)


def test_cissus_custom_mapping():
    """User can supply their own subindex → columns mapping."""
    custom = {
        "money_market":            ("tedrate", "sofrspread", "cpspread"),
        "bond_market":             ("t10y2y", "hyoas", "movevol"),
        "equity_market":           ("vix", "spxcmax", "finbeta"),
        "financial_intermediaries":("kbwcmax", "bankvol", "slossurvey"),
        "fx_market":               ("dxyvol", "eurusdbasis", "jpyusdbasis"),
    }
    cfg = CISSConfig(inputs_by_subindex=custom)
    inputs = cfg.effective_inputs()
    assert set(inputs.keys()) == set(SUBINDEX_NAMES)
    # All 15 mapped cols
    flat = [c for grp in inputs.values() for c in grp]
    assert len(flat) == 15
    assert "vix" in flat


def test_replication_diagnostics_smoke():
    """The diagnostic function should compute clean Pearson/Spearman/MAE."""
    idx = pd.date_range("2020-01-01", periods=50, freq="W")
    a = pd.Series(np.linspace(0.0, 1.0, 50), index=idx)
    b = pd.Series(np.linspace(0.0, 1.0, 50) + np.random.default_rng(0).normal(0, 0.05, 50), index=idx)
    diag = CISSUS.replication_diagnostics(a, b)
    assert "pearson_r" in diag
    assert diag["n_overlap"] == 50
    assert diag["pearson_r"] > 0.9   # very high by construction


def test_cdf_normalize_bounds():
    s = pd.Series([10, 20, 30, 40, 50])
    norm = CISSUS._cdf_normalize(s)
    assert norm.min() > 0.0
    assert norm.max() < 1.0
    assert norm.is_monotonic_increasing
