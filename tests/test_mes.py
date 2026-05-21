"""Tests for cbsrm.risk.mes."""
from __future__ import annotations

import numpy as np
import pytest

from cbsrm.risk import (
    GARCHDCCParams,
    MESMonteCarlo,
    MESResult,
    empirical_mes,
)


def _paired_returns(rho: float, n: int = 1500, sigma: float = 0.01,
                    seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.RandomState(seed)
    u = rng.normal(0, sigma, (n, 2))
    L = np.array([[1.0, 0.0],
                  [rho, np.sqrt(max(1.0 - rho ** 2, 0.0))]])
    z = u @ L.T
    return z[:, 0], z[:, 1]


# ─── Empirical MES ────────────────────────────────────────────────


def test_empirical_mes_rejects_bad_q():
    f, m = _paired_returns(0.5, n=200)
    with pytest.raises(ValueError, match="q must be"):
        empirical_mes(f, m, q=0.0)


def test_empirical_mes_rejects_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        empirical_mes(np.zeros(100), np.zeros(99))


def test_empirical_mes_rejects_short_sample():
    with pytest.raises(ValueError, match="at least 30"):
        empirical_mes(np.zeros(20), np.zeros(20))


def test_empirical_mes_perfect_correlation_equals_firm_var():
    # If firm == market exactly, MES_q = E[X | X < VaR_q] which is just
    # the ES_q (expected shortfall) of either series.
    rng = np.random.RandomState(0)
    m = rng.normal(0, 0.01, 5000)
    f = m.copy()
    res = empirical_mes(f, m, q=0.05)
    var_q = float(np.quantile(m, 0.05))
    expected = float(m[m < var_q].mean())
    assert res.mes == pytest.approx(expected, abs=1e-9)


def test_empirical_mes_independence_yields_near_zero():
    # firm uncorrelated with market → conditional mean ≈ unconditional mean ≈ 0
    f, m = _paired_returns(rho=0.0, n=10_000)
    res = empirical_mes(f, m, q=0.05)
    # f has unconditional mean ≈ 0 → MES ≈ 0
    assert abs(res.mes) < 0.002


def test_empirical_mes_high_correlation_negative():
    # firm correlated with market → MES strongly negative
    f, m = _paired_returns(rho=0.85, n=10_000)
    res = empirical_mes(f, m, q=0.05)
    assert res.mes < -0.005


def test_empirical_mes_metadata_records_method():
    f, m = _paired_returns(rho=0.5, n=500)
    res = empirical_mes(f, m, q=0.05, firm="bigbank",
                        metadata={"as_of": "2026-05-20"})
    assert isinstance(res, MESResult)
    assert res.method == "empirical"
    assert res.metadata["as_of"] == "2026-05-20"
    assert res.firm == "bigbank"


def test_empirical_mes_tail_obs_count():
    f, m = _paired_returns(rho=0.5, n=1000, seed=42)
    res = empirical_mes(f, m, q=0.05)
    # At q=0.05 expect ~50 tail observations in 1000
    assert 30 <= res.n_tail_obs <= 70
    assert res.n_total_obs == 1000


# ─── Monte-Carlo MES ──────────────────────────────────────────────


def test_mc_mes_returns_negative_for_correlated_pair():
    p = GARCHDCCParams(rho_bar=0.8, rho0=0.8)
    res = MESMonteCarlo(params=p, q=0.05, n_paths=10_000, seed=1).compute(firm="x")
    assert res.method == "monte_carlo"
    assert res.mes < 0.0
    assert res.n_tail_obs > 0


def test_mc_mes_seed_deterministic():
    p = GARCHDCCParams()
    r1 = MESMonteCarlo(params=p, q=0.05, n_paths=2000, seed=7).compute()
    r2 = MESMonteCarlo(params=p, q=0.05, n_paths=2000, seed=7).compute()
    assert r1.mes == r2.mes


def test_mc_mes_higher_correlation_more_negative():
    p_low = GARCHDCCParams(rho_bar=0.1, rho0=0.1)
    p_high = GARCHDCCParams(rho_bar=0.85, rho0=0.85)
    lo = MESMonteCarlo(params=p_low, q=0.05, n_paths=10_000, seed=42).compute()
    hi = MESMonteCarlo(params=p_high, q=0.05, n_paths=10_000, seed=42).compute()
    assert hi.mes < lo.mes
