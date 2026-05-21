"""
MES — Marginal Expected Shortfall (Acharya-Pedersen-Philippon-Richardson 2017).

Reference
---------

Acharya, V. V., Pedersen, L. H., Philippon, T., & Richardson, M. (2017).
Measuring systemic risk. *Review of Financial Studies*, 30(1), 2-47.

Definition
----------

MES is the expected one-period (typically daily) return of firm *i*
conditional on the market being in its left tail::

    MES_i(q)  =  E[ X_i  |  X_market < VaR_q(X_market) ]

where ``VaR_q(X_market)`` is the q-quantile of the market return (typically
q = 0.05, i.e. the worst 5% of market days).

A *more negative* MES means the firm loses more on average during market-
crisis days — higher systemic contribution.

Two estimation approaches
~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Empirical (historical)** — average firm return over the subset of
   historical days where market return < VaR_q. No model needed. Robust
   but only works when the sample contains enough crisis days at the
   chosen tail.

2. **Model-implied (Monte Carlo via GJR-GARCH-DCC)** — simulate paired
   firm/market returns from the parametric model, take expected firm
   return on paths where the market is in its tail. Lets you compute MES
   for scenarios that haven't yet occurred in history (counterfactual
   stress testing). Same simulator as LRMES (cbsrm.risk.garch_dcc_sim)
   but with a one-day horizon and a quantile-threshold rather than a
   cumulative-loss threshold.

Implementation
~~~~~~~~~~~~~~

Both estimators ship in CBSRM v0.5.

Validation
~~~~~~~~~~

* Empirical MES of an asset perfectly correlated with the market at q=0.05
  → equal to that asset's q=0.05 quantile.
* Empirical MES of an asset uncorrelated with the market → expected firm
  mean (irrespective of q).
* Model MES is monotone in conditional correlation ρ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cbsrm.risk.garch_dcc_sim import GARCHDCCParams, GARCHDCCSimulator


# ─── Empirical (historical) MES ────────────────────────────────────


@dataclass(frozen=True)
class MESResult:
    firm: str
    q: float
    mes: float                    # E[X_i | X_market < VaR_q]
    var_q_market: float           # the threshold
    n_tail_obs: int               # number of market-tail days in sample
    n_total_obs: int
    method: str                   # "empirical" or "monte_carlo"
    metadata: dict[str, Any] = field(default_factory=dict)


def empirical_mes(
    firm_returns: np.ndarray,
    market_returns: np.ndarray,
    *,
    q: float = 0.05,
    firm: str = "firm",
    metadata: dict[str, Any] | None = None,
) -> MESResult:
    """Historical MES from a paired return sample.

    Parameters
    ----------
    firm_returns, market_returns : (N,) arrays, same length
    q : tail probability (default 0.05 = worst 5% of market days)
    firm : label

    Returns
    -------
    MESResult
    """
    if not (0.0 < q < 1.0):
        raise ValueError(f"q must be in (0, 1); got {q}")
    f = np.asarray(firm_returns, dtype=float).ravel()
    m = np.asarray(market_returns, dtype=float).ravel()
    if f.shape[0] != m.shape[0]:
        raise ValueError("firm_returns and market_returns must have same length")
    n = f.shape[0]
    if n < 30:
        raise ValueError(f"need at least 30 obs; got {n}")

    var_q = float(np.quantile(m, q))
    tail = m < var_q
    n_tail = int(tail.sum())
    if n_tail == 0:
        # Edge case: market is constant above threshold; MES undefined
        return MESResult(
            firm=firm, q=q, mes=float("nan"),
            var_q_market=var_q, n_tail_obs=0, n_total_obs=n,
            method="empirical", metadata=dict(metadata or {}),
        )

    mes_val = float(f[tail].mean())
    return MESResult(
        firm=firm, q=q, mes=mes_val,
        var_q_market=var_q, n_tail_obs=n_tail, n_total_obs=n,
        method="empirical", metadata=dict(metadata or {}),
    )


# ─── Monte-Carlo (model-implied) MES ───────────────────────────────


@dataclass
class MESMonteCarlo:
    """One-day MES via GJR-GARCH-DCC Monte Carlo.

    Identical simulator as ``LRMESMonteCarlo`` but with horizon = 1 day and
    conditioning on a one-day market threshold rather than a horizon-
    cumulative one.
    """
    params: GARCHDCCParams = field(default_factory=GARCHDCCParams)
    q: float = 0.05
    n_paths: int = 20_000
    seed: int | None = None

    def compute(self, *, firm: str = "firm") -> MESResult:
        sim = GARCHDCCSimulator(
            params=self.params,
            horizon=1,
            n_paths=self.n_paths,
            seed=self.seed,
        )
        cum = sim.simulate()       # (n_paths, 2)
        firm_ret = cum[:, 0]
        mkt_ret = cum[:, 1]
        var_q = float(np.quantile(mkt_ret, self.q))
        tail = mkt_ret < var_q
        n_tail = int(tail.sum())
        if n_tail == 0:
            return MESResult(
                firm=firm, q=self.q, mes=float("nan"),
                var_q_market=var_q, n_tail_obs=0, n_total_obs=self.n_paths,
                method="monte_carlo",
                metadata={"params": self.params.__dict__},
            )
        mes_val = float(firm_ret[tail].mean())
        return MESResult(
            firm=firm, q=self.q, mes=mes_val,
            var_q_market=var_q, n_tail_obs=n_tail, n_total_obs=self.n_paths,
            method="monte_carlo",
            metadata={
                "params": self.params.__dict__,
                "n_paths": self.n_paths,
                "horizon_days": 1,
            },
        )
