"""
BIS Consolidated Banking Statistics — Cross-Border Claims passthrough.

Wraps the BIS Consolidated Banking Statistics (CBS) — cross-border claims
on immediate counterparty basis, quarterly, by reporting country. This
is the canonical measure of cross-border banking exposure used in
financial-stability literature (Avdjiev, du, Koepke, Shin 2018;
Aldasoro et al. 2022).

Why this matters for systemic risk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cross-border banking claims are how shocks propagate across jurisdictions.
The 2008 GFC, the 2010-12 EU sovereign-debt crisis, and the 2020 dollar-
funding stress all involved sudden retrenchment in cross-border claims.
The BIS CBS dataset is the only globally-harmonised source.

Caveats: the CBS reports on a *consolidated* basis (parent-bank's
perspective, including foreign subsidiaries) and on an *immediate
counterparty* basis (where the loan landed, not the ultimate risk).
Reading the dataset correctly requires care; see BIS's guidance at
https://www.bis.org/statistics/glossary.htm.

Reference
---------

Bank for International Settlements (2025-). "Consolidated banking
statistics — methodology." https://www.bis.org/statistics/consbankstats.htm
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from cbsrm.indicators.base import IndicatorResult
from cbsrm.indicators.bis_otc_derivatives import _resolve_col, _DATE_COL_CANDIDATES, _VALUE_COL_CANDIDATES


@dataclass
class BISCBSClaimsIndicator:
    """Passthrough wrapper for BIS consolidated banking-statistics claims."""

    id: str = "BIS-CBS-CROSS-BORDER-CLAIMS"
    version: str = "1.0.0"
    source: str = (
        "Bank for International Settlements (2025). Consolidated Banking "
        "Statistics — cross-border claims on immediate counterparty basis. "
        "https://www.bis.org/statistics/consbankstats.htm. "
        "Used under the BIS Open Data Policy with attribution."
    )

    def required_series(self) -> list[str]:
        return ["BIS:WS_CBS_PUB"]

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
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
                f"columns; got {list(data.columns)}"
            )
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
                    "Cross-border claims on immediate counterparty basis, "
                    "USD billions, BIS Consolidated Banking Statistics "
                    "(quarterly). Tracks how shocks propagate across "
                    "jurisdictions via the global banking system."
                ),
            },
        )
