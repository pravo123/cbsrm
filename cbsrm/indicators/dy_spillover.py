"""
Diebold-Yilmaz Spillover Index — cross-asset / cross-market connectedness.

Reference
---------

Diebold, F. X., & Yilmaz, K. (2009). Measuring financial asset return
and volatility spillovers, with application to global equity markets.
*Economic Journal*, 119(534), 158-171.

Diebold, F. X., & Yilmaz, K. (2012). Better to give than to receive:
Predictive directional measurement of volatility spillovers.
*International Journal of Forecasting*, 28(1), 57-66.

Methodology
-----------

The Diebold-Yilmaz spillover index measures how much of an asset's
forecast-error variance is explained by shocks to *other* assets in
the same panel, vs. its own shocks. Conceptually, it is the share of
total return variability that propagates across markets.

CBSRM uses the Pesaran-Shin (1998) generalized variance decomposition
(GFEVD) which, unlike the orthogonalized Cholesky version, is invariant
to variable ordering.

Computation
~~~~~~~~~~~

Given an N-variable panel of returns over T observations:

1. Fit a VAR(p) via OLS (default ``p=4``)
2. Compute the moving-average (MA) representation coefficients
   ``ψ_0, ψ_1, ..., ψ_{H-1}`` from the VAR coefficients (default ``H=10``)
3. For each (i, j), the generalized variance decomposition contribution::

       θ_{ij}^g(H) = σ_jj^{-1} Σ_{h=0}^{H-1} (e_i' ψ_h Σ e_j)^2
                  /  Σ_{h=0}^{H-1} (e_i' ψ_h Σ ψ_h' e_i)

4. Normalize each row to sum to 1:
   ``θ̃_{ij}^g(H) = θ_{ij}^g(H) / Σ_k θ_{ik}^g(H)``
5. Total spillover index::

       S^g(H)  =  (Σ_{i ≠ j} θ̃_{ij}^g(H))  /  N  ×  100

Output is a single number in [0, 100%]; values above ~75% historically
indicate strong cross-market coupling and contagion risk.

Inputs
~~~~~~

Any N-column DataFrame of returns (typically log returns or simple
percent returns). The default use case (4-sector US equity ETFs:
XLF / XLK / XLE / XLU) is fine for a demo; institutional users supply
their own panels.

Validation invariants
~~~~~~~~~~~~~~~~~~~~~

The unit-test suite asserts:

* Spillover is in [0, 100]
* For perfectly-uncorrelated inputs, spillover → 0
* For panels where one asset is a copy of another, spillover increases
* Index is invariant to constant rescaling of any column
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from cbsrm.indicators.base import IndicatorResult


DEFAULT_LAG_ORDER = 4
DEFAULT_FORECAST_HORIZON = 10
MIN_OBS_REQUIRED = 50


# ─── VAR + GFEVD primitives (pure numpy) ────────────────────────────


def _fit_var_ols(Y: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    """Fit a VAR(p) without intercept via OLS.

    Y: (T, N) array of returns (T observations, N variables).
    Returns:
        A: (N, N*p) stacked coefficient matrix [A_1 | A_2 | ... | A_p]
        Sigma: (N, N) residual covariance
    """
    T, N = Y.shape
    if T <= p + 1:
        raise ValueError(f"need T > p+1 observations; got T={T}, p={p}")
    # Build lagged regressor matrix: rows = T-p, cols = N*p
    X = np.zeros((T - p, N * p))
    for h in range(p):
        X[:, h * N:(h + 1) * N] = Y[p - h - 1: T - h - 1]
    Y_aligned = Y[p:]
    # Solve OLS: A.T = (X'X)^{-1} X' Y_aligned
    XtX = X.T @ X
    XtY = X.T @ Y_aligned
    coef = np.linalg.solve(XtX + 1e-10 * np.eye(N * p), XtY)  # (N*p, N)
    A = coef.T  # (N, N*p)
    resid = Y_aligned - X @ coef
    Sigma = (resid.T @ resid) / (T - p)
    return A, Sigma


def _ma_coefficients(A: np.ndarray, p: int, H: int) -> np.ndarray:
    """Compute MA(infty) representation coefficients ψ_0, ..., ψ_{H-1}.

    From VAR(p) with stacked A = [A_1 | A_2 | ... | A_p], the recursion is:
        ψ_0 = I_N
        ψ_h = Σ_{i=1}^{min(h,p)} A_i ψ_{h-i}
    """
    N = A.shape[0]
    A_list = [A[:, i * N:(i + 1) * N] for i in range(p)]
    psi = np.zeros((H, N, N))
    psi[0] = np.eye(N)
    for h in range(1, H):
        for i in range(1, min(h, p) + 1):
            psi[h] += A_list[i - 1] @ psi[h - i]
    return psi


def generalized_fevd(
    A: np.ndarray, Sigma: np.ndarray, p: int, H: int,
) -> np.ndarray:
    """Generalized FEVD (Pesaran-Shin 1998) over horizon H.

    Returns: (N, N) row-normalized matrix θ̃_{ij}.
    Row i contains the share of i's forecast-error variance attributable
    to shocks in each variable j.
    """
    psi = _ma_coefficients(A, p, H)  # (H, N, N)
    N = Sigma.shape[0]
    sigma_diag = np.diag(Sigma).copy()
    theta = np.zeros((N, N))
    for i in range(N):
        # denominator: own-variance contribution
        denom = 0.0
        for h in range(H):
            denom += float(psi[h, i] @ Sigma @ psi[h, i].T)
        for j in range(N):
            numer = 0.0
            for h in range(H):
                numer += float(psi[h, i] @ Sigma[:, j]) ** 2
            theta[i, j] = numer / max(denom, 1e-12) / max(sigma_diag[j], 1e-12)
    # Row-normalize so each row sums to 1
    row_sums = theta.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    return theta / row_sums


def total_spillover_index(theta_normalized: np.ndarray) -> float:
    """Total spillover index in [0, 100]."""
    N = theta_normalized.shape[0]
    off_diag = theta_normalized.sum() - np.trace(theta_normalized)
    return float(off_diag / N * 100.0)


# ─── Indicator ──────────────────────────────────────────────────────


@dataclass
class DYSpilloverIndicator:
    """Diebold-Yilmaz total spillover index."""

    id: str = "DY-SPILLOVER"
    version: str = "1.0.0"
    source: str = (
        "Diebold, F. X. & Yilmaz, K. (2012). Better to give than to receive: "
        "Predictive directional measurement of volatility spillovers. "
        "International Journal of Forecasting, 28(1), 57-66. "
        "Generalized variance decomposition: Pesaran & Shin (1998), Economics Letters."
    )
    lag_order: int = DEFAULT_LAG_ORDER
    forecast_horizon: int = DEFAULT_FORECAST_HORIZON
    required_columns: list[str] = field(default_factory=list)

    def required_series(self) -> list[str]:
        return list(self.required_columns)

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        if data is None or data.empty:
            return IndicatorResult(
                indicator_id=self.id, version=self.version,
                values=pd.Series(dtype=float, name=self.id),
                metadata={"source": self.source, "n_obs": 0},
            )
        cleaned = data.dropna(how="any").astype(float)
        if cleaned.shape[0] < MIN_OBS_REQUIRED:
            return IndicatorResult(
                indicator_id=self.id, version=self.version,
                values=pd.Series(dtype=float, name=self.id),
                metadata={
                    "source": self.source,
                    "n_obs": int(cleaned.shape[0]),
                    "classification": "INSUFFICIENT_HISTORY",
                    "min_obs_required": MIN_OBS_REQUIRED,
                },
            )
        Y = cleaned.values
        A, Sigma = _fit_var_ols(Y, self.lag_order)
        theta = generalized_fevd(A, Sigma, self.lag_order, self.forecast_horizon)
        S = total_spillover_index(theta)

        result_series = pd.Series([S], index=[cleaned.index[-1]], name=self.id)

        if S >= 75.0:
            classification = "HIGH_CONTAGION"
        elif S >= 50.0:
            classification = "ELEVATED_COUPLING"
        elif S >= 25.0:
            classification = "MODERATE_COUPLING"
        else:
            classification = "LOW_COUPLING"

        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=result_series,
            metadata={
                "source": self.source,
                "n_obs": int(cleaned.shape[0]),
                "n_assets": int(cleaned.shape[1]),
                "asset_names": list(cleaned.columns),
                "lag_order": self.lag_order,
                "forecast_horizon": self.forecast_horizon,
                "latest_spillover_pct": S,
                "classification": classification,
                "fevd_matrix": theta.tolist(),
                "interpretation": (
                    "Total Diebold-Yilmaz spillover index in [0,100%]. "
                    "Share of total forecast-error variance attributable to "
                    "cross-asset shocks. Higher = tighter coupling / contagion risk."
                ),
            },
        )


def spillover_series(
    returns_panel: pd.DataFrame,
    *,
    window: int = 200,
    lag_order: int = DEFAULT_LAG_ORDER,
    forecast_horizon: int = DEFAULT_FORECAST_HORIZON,
) -> pd.Series:
    """Rolling-window time series of the total spillover index.

    For each rolling window of `window` observations, fit a VAR(p),
    compute GFEVD, return total spillover. Returns a pandas Series indexed
    by the right edge of each window.
    """
    indicator = DYSpilloverIndicator(
        lag_order=lag_order, forecast_horizon=forecast_horizon,
    )
    cleaned = returns_panel.dropna(how="any").astype(float)
    n_total = cleaned.shape[0]
    if n_total < window:
        return pd.Series(dtype=float, name="DY-SPILLOVER")
    points: list[tuple[Any, float]] = []
    for end in range(window, n_total + 1):
        chunk = cleaned.iloc[end - window:end]
        res = indicator.compute(chunk)
        if res.values.size:
            points.append((chunk.index[-1], float(res.values.iloc[-1])))
    if not points:
        return pd.Series(dtype=float, name="DY-SPILLOVER")
    idx, vals = zip(*points)
    return pd.Series(list(vals), index=list(idx), name="DY-SPILLOVER")
