"""Tests for cbsrm.indicators.dy_spillover.DYSpilloverIndicator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.indicators.base import IIndicator
from cbsrm.indicators.dy_spillover import (
    DYSpilloverIndicator,
    _fit_var_ols,
    _ma_coefficients,
    generalized_fevd,
    spillover_series,
    total_spillover_index,
)


def _independent_panel(n: int = 300, k: int = 4, seed: int = 42) -> pd.DataFrame:
    """k uncorrelated Gaussian return series, length n."""
    rng = np.random.RandomState(seed)
    data = rng.normal(0, 0.01, size=(n, k))
    cols = [f"asset_{i}" for i in range(k)]
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame(data, columns=cols, index=idx)


def _coupled_panel(n: int = 300, k: int = 4, rho: float = 0.85,
                   seed: int = 42) -> pd.DataFrame:
    """k assets where each is a noisy version of a common factor."""
    rng = np.random.RandomState(seed)
    factor = rng.normal(0, 0.01, size=n)
    cols: dict[str, np.ndarray] = {}
    for i in range(k):
        idio = rng.normal(0, 0.01 * (1 - rho ** 2) ** 0.5, size=n)
        cols[f"asset_{i}"] = rho * factor + idio
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame(cols, index=idx)


# ─── Protocol conformance ──────────────────────────────────────────


def test_implements_protocol():
    assert isinstance(DYSpilloverIndicator(), IIndicator)


def test_default_lag_and_horizon():
    d = DYSpilloverIndicator()
    assert d.lag_order == 4
    assert d.forecast_horizon == 10


# ─── VAR fit primitive ──────────────────────────────────────────────


def test_fit_var_returns_correct_shapes():
    Y = _independent_panel(n=200, k=3).values
    A, Sigma = _fit_var_ols(Y, p=2)
    assert A.shape == (3, 6)
    assert Sigma.shape == (3, 3)
    # Sigma should be positive definite (diagonal positive)
    assert all(np.diag(Sigma) > 0)


def test_fit_var_rejects_short_sample():
    Y = np.zeros((3, 2))
    with pytest.raises(ValueError):
        _fit_var_ols(Y, p=4)


def test_ma_coefficients_first_is_identity():
    A = np.zeros((3, 6))   # (N=3, N*p=6 → p=2)
    psi = _ma_coefficients(A, p=2, H=5)
    np.testing.assert_array_equal(psi[0], np.eye(3))


def test_ma_coefficients_zero_var_yields_only_identity():
    A = np.zeros((3, 6))
    psi = _ma_coefficients(A, p=2, H=5)
    for h in range(1, 5):
        np.testing.assert_array_equal(psi[h], np.zeros((3, 3)))


# ─── GFEVD invariants ──────────────────────────────────────────────


def test_gfevd_rows_sum_to_one():
    Y = _independent_panel(n=300, k=4).values
    A, Sigma = _fit_var_ols(Y, p=4)
    theta = generalized_fevd(A, Sigma, p=4, H=10)
    row_sums = theta.sum(axis=1)
    np.testing.assert_allclose(row_sums, np.ones(4), atol=1e-9)


def test_total_spillover_in_zero_hundred_range():
    Y = _independent_panel(n=300, k=4).values
    A, Sigma = _fit_var_ols(Y, p=4)
    theta = generalized_fevd(A, Sigma, p=4, H=10)
    S = total_spillover_index(theta)
    assert 0.0 <= S <= 100.0


# ─── Indicator compute() ────────────────────────────────────────────


def test_compute_empty_returns_empty_result():
    res = DYSpilloverIndicator().compute(pd.DataFrame())
    assert res.values.empty
    assert res.metadata["n_obs"] == 0


def test_compute_insufficient_history():
    df = _independent_panel(n=10, k=3)
    res = DYSpilloverIndicator().compute(df)
    assert res.metadata["classification"] == "INSUFFICIENT_HISTORY"


def test_compute_independent_panel_low_spillover():
    df = _independent_panel(n=400, k=4)
    res = DYSpilloverIndicator().compute(df)
    S = res.metadata["latest_spillover_pct"]
    # Independent panels can still have low-double-digit spillover from
    # finite-sample noise; ensure clearly below "elevated" threshold
    assert S < 50.0


def test_compute_coupled_panel_higher_than_independent():
    df_indep = _independent_panel(n=400, k=4, seed=1)
    df_coupled = _coupled_panel(n=400, k=4, rho=0.9, seed=1)
    s_indep = DYSpilloverIndicator().compute(df_indep).metadata["latest_spillover_pct"]
    s_coupled = DYSpilloverIndicator().compute(df_coupled).metadata["latest_spillover_pct"]
    assert s_coupled > s_indep
    # Coupled panel should breach moderate threshold
    assert s_coupled >= 25.0


def test_compute_metadata_lists_assets():
    df = _independent_panel(n=200, k=3)
    res = DYSpilloverIndicator().compute(df)
    assert res.metadata["asset_names"] == ["asset_0", "asset_1", "asset_2"]
    assert res.metadata["n_assets"] == 3


def test_compute_invariant_to_constant_rescale():
    """Multiplying any column by a positive constant should not change S."""
    df = _coupled_panel(n=300, k=3, rho=0.6, seed=2)
    s_baseline = DYSpilloverIndicator().compute(df).metadata["latest_spillover_pct"]
    df_scaled = df.copy()
    df_scaled["asset_0"] = df_scaled["asset_0"] * 1000.0
    s_scaled = DYSpilloverIndicator().compute(df_scaled).metadata["latest_spillover_pct"]
    assert s_baseline == pytest.approx(s_scaled, abs=0.5)


def test_compute_fevd_matrix_is_serialisable():
    df = _coupled_panel(n=200, k=3, rho=0.6, seed=3)
    res = DYSpilloverIndicator().compute(df)
    fevd = res.metadata["fevd_matrix"]
    assert isinstance(fevd, list)
    assert len(fevd) == 3 and len(fevd[0]) == 3


# ─── Rolling spillover_series ──────────────────────────────────────


def test_spillover_series_returns_one_point_per_window():
    df = _coupled_panel(n=400, k=3, rho=0.6, seed=4)
    series = spillover_series(df, window=200)
    # 400 obs - 200 window + 1 = 201 rolling points
    assert len(series) == 201


def test_spillover_series_empty_when_window_too_large():
    df = _coupled_panel(n=100, k=3, rho=0.6, seed=5)
    series = spillover_series(df, window=200)
    assert series.empty
