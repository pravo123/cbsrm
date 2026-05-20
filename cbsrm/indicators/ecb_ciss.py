"""
ECB CISS wrapper — passthrough of the ECB-published Composite Indicator
of Systemic Stress for the euro area (and US, UK variants).

The ECB publishes CISS as a daily series via the SDMX API. CBSRM's
ECBCISSWrap exposes that series as an IndicatorResult, primarily for:

  1. Reference replication: CBSRM's CISSUS implementation must correlate
     highly with the ECB-published euro-area CISS during global crises.
     Use cbsrm.diagnostics.replicate(cbsrm_ciss_us, ecb_ciss_ea) to test.

  2. Direct consumption: users who want the canonical ECB CISS series
     without writing their own SDMX client.

Citation
--------

Holló, D., Kremer, M., Lo Duca, M. (2012). "CISS — A Composite Indicator
of Systemic Stress in the Financial System." ECB Working Paper 1426.
"""
from __future__ import annotations

import pandas as pd

from cbsrm.indicators.base import IndicatorResult


VARIANT_LABELS = {
    "EA": "Euro Area",
    "US": "United States",
    "UK": "United Kingdom",
}


class ECBCISSWrap:
    """Passthrough wrapper around an ECB-published CISS series."""

    id: str = "ECB-CISS"
    version: str = "1.0.0"
    source: str = (
        "European Central Bank Statistical Data Warehouse. "
        "Methodology: Holló, Kremer, Lo Duca (2012), 'CISS', ECB WP 1426. "
        "Data: https://data.ecb.europa.eu/data/datasets/CISS"
    )

    def __init__(self, variant: str = "EA") -> None:
        variant = variant.upper()
        if variant not in VARIANT_LABELS:
            raise ValueError(
                f"variant must be one of {sorted(VARIANT_LABELS)}, got {variant!r}"
            )
        self.variant = variant
        self.id = f"ECB-CISS-{variant}"

    def required_series(self) -> list[str]:
        return [f"ECB.CISS.{self.variant}"]

    def compute(self, data: pd.DataFrame | pd.Series) -> IndicatorResult:
        """Pass through the ECB-published CISS series.

        Accepts either:
          - pd.Series   — the raw series (most common; ECBSDMXClient.get_ciss_*()
                          returns this directly)
          - pd.DataFrame with one of these columns: 'ECB-CISS-{variant}',
            'ECB-CISS', the series id, or a single-column DataFrame.
        """
        s = self._resolve_series(data)
        values = s.dropna().rename(self.id).astype(float)
        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=values,
            metadata={
                "source": self.source,
                "variant": self.variant,
                "variant_label": VARIANT_LABELS[self.variant],
                "n_obs": int(values.size),
                "first_date": str(values.index.min()) if values.size else None,
                "last_date": str(values.index.max()) if values.size else None,
                "interpretation": (
                    "Values in [0, 1]. Levels above ~0.4 historically associated "
                    "with broad financial-stability events. Daily cadence."
                ),
            },
        )

    def _resolve_series(self, data: pd.DataFrame | pd.Series) -> pd.Series:
        if isinstance(data, pd.Series):
            return data
        if isinstance(data, pd.DataFrame):
            for cand in (self.id, "ECB-CISS", f"ECB.CISS.{self.variant}"):
                if cand in data.columns:
                    return data[cand]
            if data.shape[1] == 1:
                return data.iloc[:, 0]
        raise ValueError(
            f"ECBCISSWrap.compute: cannot find {self.id} column. "
            f"Got type={type(data).__name__}, columns={list(getattr(data, 'columns', []))}"
        )
