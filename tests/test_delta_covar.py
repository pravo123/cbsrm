"""Tests for cbsrm.risk.delta_covar."""
from __future__ import annotations

import numpy as np
import pytest

from cbsrm.risk import (
    CoVaRResult,
    DeltaCoVaREstimator,
    quantile_regression,
)


# ─── Quantile-regression primitive ─────────────────────────────────


def test_quantile_regression_rejects_invalid_q():
    X = np.ones((50, 1))
    y = np.random.RandomState(0).normal(size=50)
    with pytest.raises(ValueError, match="q must be"):
        quantile_regression(y, X, q=0.0)
    with pytest.raises(ValueError, match="q must be"):
        quantile_regression(y, X, q=1.0)


def test_quantile_regression_recovers_median_intercept():
    # y = constant; quantile regression at q=0.5 → intercept ≈ that constant
    n = 500
    rng = np.random.RandomState(42)
    y = 0.05 + rng.normal(0, 0.02, n)
    X = np.ones((n, 1))
    beta = quantile_regression(y, X, q=0.5, n_iter=2000, lr=0.05)
    # OLS gives mean; median should be close to the median of y
    assert beta[0] == pytest.approx(np.median(y), abs=0.02)


def test_quantile_regression_slope_recovers_correlation():
    # Generate y = 0.5 * x + noise; q=0.5 slope should be near 0.5
    rng = np.random.RandomState(1)
    n = 1000
    x = rng.normal(0, 1, n)
    noise = rng.normal(0, 0.1, n)
    y = 0.5 * x + noise
    X = np.column_stack([np.ones(n), x])
    beta = quantile_regression(y, X, q=0.5, n_iter=3000, lr=0.05)
    assert beta[1] == pytest.approx(0.5, abs=0.1)


def test_quantile_regression_shape_mismatch_raises():
    X = np.ones((10, 1))
    y = np.zeros(11)
    with pytest.raises(ValueError, match="rows"):
        quantile_regression(y, X, q=0.5)


# ─── DeltaCoVaR validation ─────────────────────────────────────────


def _paired_returns(rho: float, n: int = 1500, sigma: float = 0.01,
                    seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Generate two return series with target correlation ``rho``."""
    rng = np.random.RandomState(seed)
    u = rng.normal(0, sigma, (n, 2))
    L = np.array([[1.0, 0.0],
                  [rho, np.sqrt(max(1.0 - rho ** 2, 0.0))]])
    z = u @ L.T
    return z[:, 0], z[:, 1]   # firm, market


def test_delta_covar_estimator_rejects_q_outside_unit():
    with pytest.raises(ValueError, match="q must be"):
        DeltaCoVaREstimator(q=0.0)


def test_delta_covar_rejects_short_sample():
    e = DeltaCoVaREstimator(q=0.05)
    f, m = _paired_returns(0.5, n=20)
    with pytest.raises(ValueError, match="at least 30"):
        e.estimate(firm="x", firm_returns=f, system_returns=m)


def test_delta_covar_independent_returns_near_zero_slope():
    # firm uncorrelated with system → beta_q ≈ 0 → ΔCoVaR ≈ 0
    f, m = _paired_returns(rho=0.0, n=3000)
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="indep", firm_returns=f, system_returns=m,
    )
    assert abs(res.beta_q) < 0.20
    # ΔCoVaR magnitude small in absolute terms (less than half the firm VaR
    # magnitude)
    assert abs(res.delta_covar) < abs(res.var_q_firm) * 0.5


def test_delta_covar_high_correlation_negative_delta():
    # Strongly positive firm-system correlation: when firm in left tail,
    # system also in left tail → ΔCoVaR strongly negative
    f, m = _paired_returns(rho=0.85, n=3000)
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="big_bank", firm_returns=f, system_returns=m,
    )
    assert res.beta_q > 0.4
    assert res.delta_covar < 0.0


def test_delta_covar_median_q_yields_near_zero_delta():
    # q=0.5: VaR_q = median → CoVaR_at_VaR = CoVaR_at_median by construction
    # of the conditioning, so ΔCoVaR should be ~ 0
    f, m = _paired_returns(rho=0.7, n=3000)
    res = DeltaCoVaREstimator(q=0.5).estimate(
        firm="x", firm_returns=f, system_returns=m,
    )
    assert abs(res.delta_covar) < 1e-6


def test_delta_covar_result_has_correct_dtypes():
    f, m = _paired_returns(rho=0.6, n=1500)
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="x", firm_returns=f, system_returns=m,
    )
    assert isinstance(res, CoVaRResult)
    assert isinstance(res.delta_covar, float)
    assert res.firm == "x"
    assert res.q == 0.05
    assert res.n_obs == 1500
    assert res.has_state_vars is False


def test_delta_covar_state_vars_accepted():
    rng = np.random.RandomState(0)
    f, m = _paired_returns(rho=0.5, n=1500)
    state = rng.normal(0, 1, (1500, 2))   # 2 state variables
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="x", firm_returns=f, system_returns=m, state_vars=state,
    )
    assert res.has_state_vars is True


def test_delta_covar_state_vars_wrong_length_raises():
    f, m = _paired_returns(rho=0.5, n=1500)
    state = np.zeros((100, 1))
    with pytest.raises(ValueError, match="state_vars"):
        DeltaCoVaREstimator(q=0.05).estimate(
            firm="x", firm_returns=f, system_returns=m, state_vars=state,
        )


def test_delta_covar_metadata_preserved():
    f, m = _paired_returns(rho=0.6, n=1500)
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="x", firm_returns=f, system_returns=m,
        metadata={"as_of": "2026-05-20"},
    )
    assert res.metadata["as_of"] == "2026-05-20"
