"""
OFR FSI wrapper — Office of Financial Research Financial Stress Index.

A passthrough indicator (like STLFSIWrap) that exposes the OFR FSI
composite + 5 subindex contributions as a CBSRM-shaped IndicatorResult.

The OFR FSI is the second canonical US daily systemic-stress index
(alongside the Chicago Fed NFCI). Methodology: Monin (2019), "The OFR
Financial Stress Index", *Risks* 7(1): 25. Composite from 33 raw
indicators across 5 categories: credit, equity valuation, funding,
safe assets, volatility.

Used in CBSRM as a SECOND independent stress measurement to cross-check
CISSUSCanonical (different methodology — dynamic factor model vs.
portfolio-theoretic correlation aggregation — but both daily US).
A high CISSUSCanonical/OFR-FSI correlation during crisis windows is a
positive replication signal for CISS-US.
"""
from __future__ import annotations

import pandas as pd

from cbsrm.indicators.base import IndicatorResult


# Canonical OFR FSI column ids we expect — the CSV's exact column names
# have varied. Operators can override at compute time.
DEFAULT_COMPOSITE_COL_CANDIDATES = (
    "OFR FSI", "OFR_FSI", "Financial Stress Index", "OFRFSI", "OFR Financial Stress Index",
)
DEFAULT_SUBINDEX_COL_CANDIDATES = {
    "credit":           ("Credit",),
    "equity_valuation": ("Equity valuation", "Equity Valuation", "Equities"),
    "funding":          ("Funding",),
    "safe_assets":      ("Safe assets", "Safe Assets"),
    "volatility":       ("Volatility",),
}


class OFRFSIWrap:
    """Passthrough wrapper around the OFR Financial Stress Index."""

    id: str = "OFR-FSI"
    version: str = "1.0.0"
    source: str = (
        "Office of Financial Research (US Department of the Treasury). "
        "Monin, P. (2019). 'The OFR Financial Stress Index.' "
        "Risks 7(1): 25. https://www.financialresearch.gov/financial-stress-index/"
    )

    def __init__(
        self,
        composite_col: str | None = None,
        subindex_cols: dict[str, str] | None = None,
    ) -> None:
        self._composite_col_override = composite_col
        self._subindex_cols_override = subindex_cols

    def required_series(self) -> list[str]:
        # OFR FSI comes as one CSV with multiple columns; the canonical
        # "series id" at our layer is just the composite column.
        return ["OFR FSI"]

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """Pass through the OFR FSI composite + subindex breakdown."""
        comp_col = self._resolve_composite_column(data)
        if comp_col is None:
            raise ValueError(
                f"OFRFSIWrap.compute: no recognizable composite column in "
                f"{list(data.columns)}. Pass composite_col=... to override."
            )

        values = data[comp_col].dropna().rename(self.id).astype(float)

        # Subindex breakdown if available
        sub_cols = self._resolve_subindex_columns(data)
        if sub_cols:
            sub = data[list(sub_cols.values())].rename(
                columns={v: k for k, v in sub_cols.items()}
            ).astype(float)
            sub = sub.loc[values.index]
        else:
            sub = None

        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=values,
            subindex_values=sub,
            metadata={
                "source": self.source,
                "n_obs": int(values.size),
                "first_date": str(values.index.min()) if values.size else None,
                "last_date": str(values.index.max()) if values.size else None,
                "composite_column_used": comp_col,
                "subindex_columns_used": sub_cols or {},
                "interpretation": (
                    "Z-score scale; 0 = average level of stress over the full "
                    "history. Positive = above-average stress, negative = below. "
                    "Daily cadence, US scope."
                ),
            },
        )

    # ─── Column resolution ────────────────────────────────────────────

    def _resolve_composite_column(self, df: pd.DataFrame) -> str | None:
        if self._composite_col_override:
            return (self._composite_col_override
                    if self._composite_col_override in df.columns else None)
        for cand in DEFAULT_COMPOSITE_COL_CANDIDATES:
            if cand in df.columns:
                return cand
        return None

    def _resolve_subindex_columns(self, df: pd.DataFrame) -> dict[str, str]:
        if self._subindex_cols_override:
            return {k: v for k, v in self._subindex_cols_override.items()
                    if v in df.columns}
        out: dict[str, str] = {}
        for canonical, cands in DEFAULT_SUBINDEX_COL_CANDIDATES.items():
            for c in cands:
                if c in df.columns:
                    out[canonical] = c
                    break
        return out
