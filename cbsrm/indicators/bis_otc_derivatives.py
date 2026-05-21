"""
BIS OTC Derivatives Notional Outstanding — passthrough indicator wrapper.

Wraps the BIS Statistical Bulletin's OTC derivatives statistics (semi-
annual). Reports gross notional outstanding by risk class:

* interest rate (the dominant ~80% of all OTC derivatives notional)
* foreign exchange (~10%)
* equity-linked (~1%)
* commodity (~1%)
* credit default swaps (~3%)
* other (residual)

Why this matters for systemic risk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Gross notional is the canonical measure for sizing the OTC derivatives
market. While gross market value is smaller (typically 2-3% of notional),
the notional figure is what regulators, supervisors, and academic papers
quote in headlines. The semi-annual BIS Triennial Survey, plus the
quarterly BIS Statistical Bulletin updates, is the only globally-
consistent source. (NY Fed, BoE, and ECB publish jurisdiction-specific
slices but harmonisation is BIS-mediated.)

Reference
---------

Bank for International Settlements (2025-). "Statistics on OTC derivatives."
https://www.bis.org/statistics/derstats.htm

This wrapper passes the BIS CSV through unmodified — the indicator's role
is to make the data accessible under the same `IIndicator` Protocol that
backs every other CBSRM stress / macro / risk-pricing measure, so it can
flow through the audit chain and the unified API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from cbsrm.indicators.base import IndicatorResult


# Heuristic column resolution — BIS occasionally renames; we accept any of
# the well-known column names and normalise on output.
_VALUE_COL_CANDIDATES = ("OBS_VALUE", "obs_value", "value", "Value")
_DATE_COL_CANDIDATES = ("TIME_PERIOD", "time_period", "date", "Date")


def _resolve_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


@dataclass
class BISOTCDerivativesIndicator:
    """Passthrough wrapper for the BIS OTC derivatives notional series."""

    id: str = "BIS-OTC-DERIVATIVES-NOTIONAL"
    version: str = "1.0.0"
    source: str = (
        "Bank for International Settlements (2025). Statistics on OTC "
        "derivatives. https://www.bis.org/statistics/derstats.htm. "
        "Used under the BIS Open Data Policy with attribution."
    )

    def required_series(self) -> list[str]:
        # The series identifier is the BIS dataflow + key
        return ["BIS:WS_OTC_DERIV2"]

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """Compute the indicator from a BIS-shaped DataFrame.

        The CSV from BIS has many columns (dimension tags + ``OBS_VALUE`` +
        ``TIME_PERIOD``). We extract the value series indexed by period.
        """
        if data is None or data.empty:
            return IndicatorResult(
                indicator_id=self.id, version=self.version,
                values=pd.Series(dtype=float, name=self.id),
                metadata={"source": self.source, "n_obs": 0},
            )
        value_col = _resolve_col(data, _VALUE_COL_CANDIDATES)
        date_col = _resolve_col(data, _DATE_COL_CANDIDATES)
        if value_col is None or date_col is None:
            raise ValueError(
                f"{self.id}.compute() could not find OBS_VALUE / TIME_PERIOD "
                f"columns in BIS dataframe; got {list(data.columns)}"
            )
        # Period parsing — BIS uses YYYY-Sx for semi-annual, YYYY-Qx for
        # quarterly, YYYY-MM for monthly. pandas to_datetime handles most;
        # we fall back to string-sorted if not.
        try:
            idx = pd.to_datetime(data[date_col])
        except (ValueError, TypeError):
            idx = pd.Index(data[date_col].astype(str))
        values = pd.to_numeric(data[value_col], errors="coerce")
        series = pd.Series(values.values, index=idx, name=self.id).dropna().sort_index()

        latest_val = float(series.iloc[-1]) if not series.empty else float("nan")
        latest_date = str(series.index.max()) if not series.empty else None

        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=series,
            metadata={
                "source": self.source,
                "n_obs": int(series.size),
                "first_date": str(series.index.min()) if not series.empty else None,
                "last_date": latest_date,
                "latest_value": latest_val,
                "interpretation": (
                    "Gross notional outstanding of OTC derivatives, "
                    "USD billions, BIS Statistical Bulletin table D5.1 "
                    "(semi-annual). Interest-rate derivatives are typically "
                    "~80% of the global aggregate."
                ),
            },
        )
