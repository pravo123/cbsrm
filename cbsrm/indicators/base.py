"""
Indicator protocol + result type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@dataclass
class IndicatorResult:
    """Output of one indicator computation."""
    indicator_id: str
    version: str
    values: pd.Series
    subindex_values: pd.DataFrame | None = None     # per-subindex breakdown if applicable
    metadata: dict[str, Any] = field(default_factory=dict)
    audit_row_id: int | None = None                 # filled by cbsrm.audit if used

    @property
    def latest(self) -> tuple[pd.Timestamp, float] | None:
        if self.values.empty:
            return None
        return self.values.index[-1], float(self.values.iloc[-1])


@runtime_checkable
class IIndicator(Protocol):
    """Protocol every indicator class implements."""
    id: str
    version: str
    source: str

    def required_series(self) -> list[str]:
        """Return list of upstream series identifiers this indicator needs."""
        ...

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """Compute the indicator from a DataFrame of required series."""
        ...
