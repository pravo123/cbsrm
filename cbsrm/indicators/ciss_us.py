"""
CISS-US — Composite Indicator of Systemic Stress, US application.
==================================================================

Methodology
-----------

Follows the ECB CISS methodology of Holló, Kremer & Lo Duca (2012,
ECB Working Paper 1426) applied to US data. The construction has
three stages:

  1. RAW INPUT TRANSFORMATION
     For each of N=15 raw stress indicators, transform to the empirical
     unit interval [0,1] via the cumulative-distribution-function rank
     of each observation against the full historical sample. This makes
     all inputs scale-free and comparable.

  2. SUBINDEX AGGREGATION
     The 15 inputs are grouped into 5 subindices (3 inputs each),
     corresponding to 5 segments of the financial system:
       - Money market
       - Bond market
       - Equity market
       - Financial intermediaries
       - Foreign exchange market
     Each subindex is the arithmetic mean of its 3 normalized inputs.

  3. PORTFOLIO-THEORETIC AGGREGATION (the methodology's signature)
     The composite is NOT a simple weighted average of the subindices.
     Instead, the 5-vector of subindices s_t is combined as:

         CISS_t = (w ⊙ s_t)' · C_t · (w ⊙ s_t)

     where w is a 5-vector of segment weights (defaults: equal),
     ⊙ is element-wise product, and C_t is a 5x5 time-varying
     correlation matrix estimated by exponentially-weighted moving
     covariance (EWMA, λ = 0.93 per the ECB default).

     This non-linear aggregation captures the "systemic" property:
     when subindex stresses co-move (correlations rise toward 1),
     the composite amplifies; when stresses are idiosyncratic (low
     correlations), the composite stays subdued even if individual
     subindices are elevated.

US-specific input mapping
--------------------------

The ECB published the methodology but never produced a US series.
The CBSRM US mapping (which is itself a contribution worth publishing)
is:

  Money market:
    - TED spread (TEDRATE)
    - SOFR – IORB spread (SOFR – IORB)
    - 3M Commercial Paper – T-Bill spread

  Bond market:
    - 10Y – 2Y Treasury yield spread |level|         (T10Y2Y)
    - High-yield OAS                                  (BAMLH0A0HYM2)
    - 10Y Treasury realized volatility (proxy)

  Equity market:
    - VIX                                              (VIXCLS)
    - S&P 500 CMAX (max-drawdown over rolling window)
    - S&P 500 financials beta

  Financial intermediaries:
    - KBW Bank Index CMAX
    - Bank stock realized volatility
    - Senior Loan Officer Survey "tightening" diffusion (proxy)

  Foreign exchange:
    - Trade-weighted USD volatility                   (DTWEXBGS)
    - EUR/USD basis swap spread (proxy)
    - JPY/USD basis swap spread (proxy)

For v0.1 the indicator accepts any 15-column DataFrame; the mapping
to FRED mnemonics is intentionally configurable. Subsequent releases
will harden the canonical mapping and provide a ``CISSUSCanonical``
subclass with frozen mnemonics for replication.

References
----------

Holló, D., Kremer, M., Lo Duca, M. (2012). "CISS — A Composite Indicator
of Systemic Stress in the Financial System." ECB Working Paper 1426.
https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1426.pdf
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cbsrm.indicators.base import IndicatorResult


DEFAULT_EWMA_LAMBDA = 0.93
DEFAULT_SUBINDEX_WEIGHTS = (0.2, 0.2, 0.2, 0.2, 0.2)
SUBINDEX_NAMES = (
    "money_market",
    "bond_market",
    "equity_market",
    "financial_intermediaries",
    "fx_market",
)


@dataclass(frozen=True)
class CISSConfig:
    """CISS construction parameters."""
    ewma_lambda: float = DEFAULT_EWMA_LAMBDA          # EWMA decay for time-varying correlation
    weights: tuple[float, ...] = DEFAULT_SUBINDEX_WEIGHTS
    min_history: int = 60                              # minimum obs before computing
    # Mapping: subindex_name -> list of raw column names in input DataFrame.
    # Defaults are placeholders — operator MUST override for live use.
    inputs_by_subindex: dict[str, tuple[str, ...]] | None = None

    def effective_inputs(self) -> dict[str, tuple[str, ...]]:
        if self.inputs_by_subindex:
            return self.inputs_by_subindex
        return {name: tuple(f"{name}_{i+1}" for i in range(3)) for name in SUBINDEX_NAMES}


class CISSUS:
    """CISS methodology applied to US public data.

    Construct with a config; call compute(df) where df has 15 columns
    (3 per subindex, see config). Returns IndicatorResult with both
    the composite series and the per-subindex breakdown.
    """

    id: str = "CISS-US"
    version: str = "0.1.0"
    source: str = (
        "Methodology: Holló, Kremer, Lo Duca (2012), 'CISS', ECB WP 1426. "
        "US extension: CBSRM v0.1, https://github.com/pravo123/cbsrm."
    )

    def __init__(self, config: CISSConfig | None = None) -> None:
        self.config = config or CISSConfig()
        w = self.config.weights
        if len(w) != 5:
            raise ValueError("weights must have length 5")
        if abs(sum(w) - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0; got {sum(w)}")
        if any(x < 0 for x in w):
            raise ValueError("weights must be non-negative")
        if not 0.0 < self.config.ewma_lambda < 1.0:
            raise ValueError("ewma_lambda must be in (0, 1)")

    # ─── Protocol methods ─────────────────────────────────────────────

    def required_series(self) -> list[str]:
        """Flat list of all 15 raw series names (default placeholders)."""
        out: list[str] = []
        for series in self.config.effective_inputs().values():
            out.extend(series)
        return out

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """Compute CISS-US from a DataFrame with the configured columns."""
        inputs = self.config.effective_inputs()
        missing = [c for grp in inputs.values() for c in grp if c not in data.columns]
        if missing:
            raise ValueError(f"CISSUS.compute missing columns: {missing}")

        # 1. CDF-normalize each raw input to [0, 1]
        normalized = pd.DataFrame(index=data.index)
        for grp in inputs.values():
            for col in grp:
                normalized[col] = self._cdf_normalize(data[col])

        # 2. Aggregate each subindex (simple mean across its 3 inputs)
        sub = pd.DataFrame(index=normalized.index)
        for name, cols in inputs.items():
            sub[name] = normalized[list(cols)].mean(axis=1)

        # Drop rows where any subindex is NaN
        sub = sub.dropna()
        if len(sub) < self.config.min_history:
            raise ValueError(
                f"CISSUS needs at least {self.config.min_history} obs; got {len(sub)}"
            )

        # 3. Portfolio-theoretic composite with time-varying correlation
        composite = self._portfolio_composite(sub)

        result_values = pd.Series(composite, index=sub.index, name=self.id)

        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=result_values,
            subindex_values=sub,
            metadata={
                "source": self.source,
                "ewma_lambda": self.config.ewma_lambda,
                "weights": list(self.config.weights),
                "subindex_names": list(SUBINDEX_NAMES),
                "input_mapping": {k: list(v) for k, v in inputs.items()},
                "n_obs": int(result_values.size),
                "interpretation": (
                    "Values in [0,1]. Stress is amplified non-linearly when "
                    "subindices co-move (rising correlations) — the systemic "
                    "property. Levels above ~0.4 historically associated with "
                    "broad financial-stability events."
                ),
            },
        )

    # ─── Replication diagnostic ───────────────────────────────────────

    @staticmethod
    def replication_diagnostics(
        cbsrm_series: pd.Series, canonical: pd.Series,
    ) -> dict[str, float]:
        """Compare CBSRM-computed CISS-US against a canonical reference.

        Common references for sanity:
          - ECB CISS for euro area (similar methodology, different geography
            — should co-move in global crises but not always)
          - STLFSI4 (very different methodology but should correlate ~0.6+
            during crisis windows)

        Returns Pearson r, Spearman ρ, mean-absolute-error of standardized
        series, and overlap window size.
        """
        joined = pd.concat([cbsrm_series.rename("cbsrm"),
                            canonical.rename("canon")], axis=1).dropna()
        if joined.empty:
            return {"n_overlap": 0}

        a, b = joined["cbsrm"], joined["canon"]
        # Standardize both to z-scores before comparing
        az = (a - a.mean()) / a.std(ddof=0)
        bz = (b - b.mean()) / b.std(ddof=0)
        return {
            "n_overlap": int(len(joined)),
            "pearson_r": float(a.corr(b, method="pearson")),
            "spearman_rho": float(a.corr(b, method="spearman")),
            "mae_zscore": float((az - bz).abs().mean()),
            "cbsrm_mean": float(a.mean()),
            "cbsrm_std": float(a.std(ddof=0)),
            "canon_mean": float(b.mean()),
            "canon_std": float(b.std(ddof=0)),
        }

    # ─── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _cdf_normalize(s: pd.Series) -> pd.Series:
        """Map values to [0,1] via empirical-CDF rank.

        Equivalent to rank / (N+1) of the full-sample distribution.
        Robust to outliers and unit-free.
        """
        s = s.astype(float)
        clean = s.dropna()
        if clean.empty:
            return s
        ranks = clean.rank(method="average")
        scaled = ranks / (len(clean) + 1)
        out = pd.Series(index=s.index, dtype=float)
        out.loc[clean.index] = scaled.values
        return out

    def _portfolio_composite(self, sub: pd.DataFrame) -> np.ndarray:
        """CISS_t = (w ⊙ s_t)' C_t (w ⊙ s_t), C_t = EWMA correlation."""
        w = np.array(self.config.weights, dtype=float)
        lam = self.config.ewma_lambda
        S = sub.to_numpy(dtype=float)  # T × 5
        T, K = S.shape

        # EWMA-weighted demeaned product → covariance → correlation
        # Use running EWMA via recursion: cov_t = lam*cov_{t-1} + (1-lam)*x_t x_t'
        cov = np.zeros((K, K))
        means = np.zeros(K)
        comp = np.zeros(T)

        # Bootstrap with full-sample covariance for the first row to avoid divide-by-zero
        cov = np.cov(S.T, ddof=0)
        means = S.mean(axis=0)

        for t in range(T):
            x = S[t] - means
            # Update EWMA covariance and mean
            cov = lam * cov + (1 - lam) * np.outer(x, x)
            means = lam * means + (1 - lam) * S[t]
            # Convert covariance to correlation
            sd = np.sqrt(np.diag(cov))
            sd_safe = np.where(sd > 1e-12, sd, 1e-12)
            corr = cov / np.outer(sd_safe, sd_safe)
            np.clip(corr, -1.0, 1.0, out=corr)
            # Composite
            ws = w * S[t]
            comp[t] = float(ws @ corr @ ws)

        # Squash to [0,1] by clipping (composite is non-negative by construction
        # of weights * subindices in [0,1] and PSD correlation; numerical drift
        # can produce trivially negative or >1 values which we clip).
        return np.clip(comp, 0.0, 1.0)
