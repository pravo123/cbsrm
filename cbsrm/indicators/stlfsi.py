"""
STLFSI4 wrapper — the sanity baseline.

Wraps the St. Louis Fed Financial Stress Index (version 4) directly from FRED.
Useful as:
  - A canonical "ground truth" stress index to compare CBSRM-computed indices
    against. If our CISS-US doesn't broadly co-move with STLFSI4 in stress
    windows (2008Q4, 2020Q1, 2023Q1), the methodology is wrong.
  - A v0.1 first-shippable indicator that requires no methodology re-derivation.

Source
------

  Federal Reserve Bank of St. Louis (2025).
  "St. Louis Fed Financial Stress Index (STLFSI4)."
  https://fred.stlouisfed.org/series/STLFSI4

The index is a weekly-Thursday principal-component composite of 18 input series
(yields, spreads, vol). Zero indicates "normal financial market conditions";
positive values are above-average stress, negative below.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from cbsrm.indicators.base import IndicatorResult


class STLFSIWrap:
    """Passthrough wrapper around FRED STLFSI4."""

    id: str = "STLFSI4"
    version: str = "1.0.0"
    source: str = (
        "Federal Reserve Bank of St. Louis (2025). "
        "St. Louis Fed Financial Stress Index. "
        "Series ID STLFSI4. https://fred.stlouisfed.org/series/STLFSI4"
    )

    def required_series(self) -> list[str]:
        return ["STLFSI4"]

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """data must contain a 'STLFSI4' column. Returns the series verbatim."""
        if "STLFSI4" not in data.columns:
            raise ValueError(
                f"{self.id}.compute() requires column 'STLFSI4' in data; "
                f"got columns {list(data.columns)}"
            )
        values = data["STLFSI4"].dropna().rename(self.id)
        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=values,
            metadata={
                "source": self.source,
                "n_obs": int(values.size),
                "first_date": str(values.index.min()) if values.size else None,
                "last_date": str(values.index.max()) if values.size else None,
                "interpretation": (
                    "0 = normal conditions; >0 above-average stress; "
                    "<0 below-average. Weekly-Thursday cadence."
                ),
            },
        )
