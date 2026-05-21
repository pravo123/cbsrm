"""
ΔCoVaR — Conditional Value-at-Risk delta (Adrian & Brunnermeier 2016).

Reference
---------

Adrian, T., & Brunnermeier, M. K. (2016). CoVaR. *American Economic Review*,
106(7), 1705-1741.

Definition
----------

CoVaR is the q-quantile (e.g. q=0.05) of the financial system's return
conditional on an institution being at its q-quantile::

    CoVaR_{system | X_i = VaR_{q,i}}  =  q-quantile of  X_{sys}  |  X_i = VaR_{q,i}

The *delta* version measures the marginal contribution of firm i to system
distress::

    ΔCoVaR_i  =  CoVaR_{sys | X_i = VaR_{q,i}}  -  CoVaR_{sys | X_i = median_i}

ΔCoVaR < 0 (system return more negative when firm is in distress) measures
how much the firm contributes to system-wide tail risk. The more negative,
the larger the firm's systemic contribution.

Estimation
~~~~~~~~~~

We estimate the conditional quantiles by linear quantile regression
(Koenker-Bassett 1978):

    Q_q(X_{sys,t}) =  α_q  +  β_q * X_{i,t}  +  γ_q' * M_{t-1}

where ``M_{t-1}`` is an optional vector of state-variable lags (yield curve,
credit spread, vol). If ``M`` is omitted, the model is just univariate.

ΔCoVaR is then::

    ΔCoVaR_i  =  β_q * ( VaR_{q,i}  -  median_i )

where ``VaR_{q,i}`` is the q-quantile of firm i's returns and ``median_i``
is the firm's median return — both empirical from the sample.

Implementation
~~~~~~~~~~~~~~

Quantile regression implemented from scratch using scipy.optimize on the
pinball loss::

    L_q(u) = u * (q - I(u < 0))

This avoids a hard dependency on statsmodels while remaining numerically
sound for the sample sizes typical of financial-stability research
(N ~ 1000-10000).

Validation properties
~~~~~~~~~~~~~~~~~~~~~

* β_q on an independent (zero-correlated) return pair → 0
* β_q on perfectly-correlated returns → 1
* ΔCoVaR_q with q=0.5 → 0 (median - median = 0)
* ΔCoVaR_q with q → 0 → arbitrarily negative for positively-correlated firms

The unit-test suite asserts each.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ─── Quantile-regression primitive (from scratch) ──────────────────


def _pinball_loss(beta: np.ndarray, X: np.ndarray, y: np.ndarray,
                  q: float) -> float:
    """Sum of pinball losses for quantile regression."""
    resid = y - X @ beta
    return float(np.sum(np.where(resid >= 0, q * resid, (q - 1.0) * resid)))


def _pinball_grad(beta: np.ndarray, X: np.ndarray, y: np.ndarray,
                  q: float) -> np.ndarray:
    """Subgradient of pinball loss (treat boundary as 0)."""
    resid = y - X @ beta
    sign = np.where(resid >= 0, -q, -(q - 1.0))  # d/dbeta of loss wrt beta
    return X.T @ sign


def quantile_regression(
    y: np.ndarray,
    X: np.ndarray,
    q: float,
    *,
    n_iter: int = 1500,
    lr: float = 0.01,
    seed: int | None = None,
) -> np.ndarray:
    """Fit a linear quantile regression Q_q(y | X) = X @ beta.

    Uses gradient descent on the pinball loss. For research / financial-
    stability use this converges adequately for N ≤ 10000.

    Parameters
    ----------
    y : (N,) array — dependent variable (e.g. system returns)
    X : (N, P) array — covariates (must include a column of ones if
        an intercept is desired)
    q : quantile in (0, 1)
    n_iter : number of gradient-descent iterations
    lr : learning rate
    seed : RNG seed for the OLS-warm-start initialisation (None = stable warm)

    Returns
    -------
    beta : (P,) array — fitted coefficients
    """
    if not (0.0 < q < 1.0):
        raise ValueError(f"q must be in (0, 1); got {q}")
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    if X.shape[0] != y.shape[0]:
        raise ValueError(f"X has {X.shape[0]} rows, y has {y.shape[0]}")

    # OLS warm start (closed-form for the L2 solution)
    XtX = X.T @ X
    Xty = X.T @ y
    try:
        beta = np.linalg.solve(XtX + 1e-8 * np.eye(X.shape[1]), Xty)
    except np.linalg.LinAlgError:
        beta = np.zeros(X.shape[1])

    # Gradient descent on pinball loss with adaptive step decay
    N = X.shape[0]
    step = lr / max(N, 1)
    for k in range(n_iter):
        g = _pinball_grad(beta, X, y, q) / N
        beta = beta - step * g
        # Slow step decay
        if (k + 1) % 250 == 0:
            step *= 0.6
    return beta


# ─── ΔCoVaR estimator ──────────────────────────────────────────────


@dataclass(frozen=True)
class CoVaRResult:
    """One ΔCoVaR estimate for one firm."""
    firm: str
    q: float
    beta_q: float                  # quantile-regression slope on firm return
    var_q_firm: float              # VaR_q of firm
    median_firm: float
    covar_at_var: float            # CoVaR conditional on firm at VaR_q
    covar_at_median: float         # CoVaR conditional on firm at median
    delta_covar: float             # = covar_at_var - covar_at_median
    n_obs: int
    has_state_vars: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeltaCoVaREstimator:
    """Estimate ΔCoVaR for one firm vs the system."""

    q: float = 0.05
    include_intercept: bool = True

    def __post_init__(self) -> None:
        if not (0.0 < self.q < 1.0):
            raise ValueError(f"q must be in (0, 1); got {self.q}")

    def estimate(
        self,
        *,
        firm: str,
        firm_returns: np.ndarray,
        system_returns: np.ndarray,
        state_vars: np.ndarray | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CoVaRResult:
        """Fit and return ΔCoVaR estimate.

        Parameters
        ----------
        firm : label for the firm
        firm_returns : (N,) array of firm returns
        system_returns : (N,) array of aggregate system returns
        state_vars : (N, K) optional array of lagged state variables
            (e.g. yield curve, vol, credit spread). Recommended for
            real applications; if omitted, falls back to univariate.

        Returns
        -------
        CoVaRResult
        """
        x = np.asarray(firm_returns, dtype=float).ravel()
        y = np.asarray(system_returns, dtype=float).ravel()
        if x.shape[0] != y.shape[0]:
            raise ValueError("firm_returns and system_returns must have same length")
        n = x.shape[0]
        if n < 30:
            raise ValueError(f"need at least 30 observations; got {n}")

        # Build design matrix
        cols = []
        if self.include_intercept:
            cols.append(np.ones(n))
        cols.append(x)
        if state_vars is not None:
            S = np.asarray(state_vars, dtype=float)
            if S.ndim == 1:
                S = S[:, None]
            if S.shape[0] != n:
                raise ValueError("state_vars row count must match returns")
            cols.append(S)
        X = np.column_stack(cols)

        # Fit quantile regression at level q
        beta = quantile_regression(y, X, self.q)

        # Slope on firm return is the column AFTER intercept (if present)
        firm_col_idx = 1 if self.include_intercept else 0
        beta_q = float(beta[firm_col_idx])

        # VaR_q of firm and its median (empirical)
        var_q_firm = float(np.quantile(x, self.q))
        median_firm = float(np.quantile(x, 0.5))

        # CoVaR at two conditioning points: use state vars at their means
        # for the comparison so only the firm-return contribution differs.
        def _covar_at(firm_value: float) -> float:
            row = []
            if self.include_intercept:
                row.append(1.0)
            row.append(firm_value)
            if state_vars is not None:
                row.extend(np.mean(np.asarray(state_vars, dtype=float),
                                   axis=0).tolist())
            return float(np.array(row) @ beta)

        covar_at_var = _covar_at(var_q_firm)
        covar_at_median = _covar_at(median_firm)
        delta_covar = covar_at_var - covar_at_median

        return CoVaRResult(
            firm=firm,
            q=self.q,
            beta_q=beta_q,
            var_q_firm=var_q_firm,
            median_firm=median_firm,
            covar_at_var=covar_at_var,
            covar_at_median=covar_at_median,
            delta_covar=delta_covar,
            n_obs=n,
            has_state_vars=state_vars is not None,
            metadata=dict(metadata or {}),
        )
