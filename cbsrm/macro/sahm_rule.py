"""
Sahm Rule recession indicator.

Reference
---------

Sahm, Claudia (2019). "Direct stimulus payments to individuals." In
*Recession Ready: Fiscal Policies to Stabilize the American Economy*,
Hamilton Project, Brookings Institution.

Updated and maintained as a real-time recession indicator by the
Federal Reserve Bank of St. Louis (series ``SAHMREALTIME`` on FRED).

Methodology
-----------

The Sahm Rule signals the start of a US recession when the three-month
moving average of the national unemployment rate (FRED ``UNRATE``) rises
0.50 percentage points or more above its minimum over the trailing 12
months. Formally::

    sahm_t = mean(UNRATE_{t-2}, UNRATE_{t-1}, UNRATE_t)
           − min(mean(UNRATE_{t-14}, ..., UNRATE_t-12), ...)

The rule has triggered for every US recession since 1970. False positives
historically are rare (one borderline trigger in 2024 that ultimately
resolved without a NBER-dated recession). It is the most-watched
real-time recession indicator in macro circles in 2024-25.

CBSRM publishes our own computation from ``UNRATE`` (rather than using
the St. Louis Fed's pre-computed ``SAHMREALTIME`` series) for two reasons:

1. **Transparency.** Every observation in the output series can be
   traced back to the underlying ``UNRATE`` print via the audit chain.
2. **Methodology consistency.** All cbsrm macro indicators share the
   same Protocol; the rule fits the existing framework cleanly without
   a one-off passthrough wrapper.

Classifications
~~~~~~~~~~~~~~~

* ``RECESSION_TRIGGERED`` — Sahm value >= 0.50 pp (the strict rule)
* ``EARLY_WARNING`` — 0.30 <= Sahm < 0.50 pp (literature-soft threshold)
* ``NORMAL`` — Sahm < 0.30 pp
* ``INSUFFICIENT_HISTORY`` — fewer than 15 monthly observations
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from cbsrm.i18n import with_i18n
from cbsrm.indicators.base import IndicatorResult


THRESHOLD_RECESSION_PP = 0.50
THRESHOLD_EARLY_WARNING_PP = 0.30
MIN_OBS_REQUIRED = 15        # need at least 3-month + 12-month windows = 15 months


@dataclass
class SahmRuleIndicator:
    """Sahm Rule recession indicator."""

    id: str = "SAHM-RULE-US"
    version: str = "1.0.0"
    source: str = (
        "Sahm, C. (2019). Direct stimulus payments to individuals, in "
        "Recession Ready: Fiscal Policies to Stabilize the American "
        "Economy, Hamilton Project / Brookings. Computed from FRED "
        "UNRATE (Civilian Unemployment Rate, monthly SA). "
        "https://fred.stlouisfed.org/series/UNRATE"
    )
    series_id: str = "UNRATE"
    threshold_recession_pp: float = THRESHOLD_RECESSION_PP
    threshold_early_warning_pp: float = THRESHOLD_EARLY_WARNING_PP

    def required_series(self) -> list[str]:
        return [self.series_id]

    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        col = self.series_id
        if col not in data.columns:
            raise ValueError(
                f"{self.id}.compute() requires column '{col}'; "
                f"got columns {list(data.columns)}"
            )
        unrate = data[col].dropna().astype(float)
        if unrate.empty:
            return IndicatorResult(
                indicator_id=self.id,
                version=self.version,
                values=pd.Series(dtype=float, name=self.id),
                metadata=with_i18n({"source": self.source, "n_obs": 0},
                                   "sahm_rule.interpretation"),
            )

        # 3-month moving average of UNRATE
        three_m_avg = unrate.rolling(window=3, min_periods=3).mean()
        # 12-month trailing minimum of that 3M average
        twelve_m_min = three_m_avg.rolling(window=12, min_periods=12).min()
        sahm = (three_m_avg - twelve_m_min).rename(self.id).dropna()

        if sahm.empty:
            return IndicatorResult(
                indicator_id=self.id,
                version=self.version,
                values=pd.Series(dtype=float, name=self.id),
                metadata=with_i18n({
                    "source": self.source,
                    "n_obs": 0,
                    "classification": "INSUFFICIENT_HISTORY",
                }, "sahm_rule.interpretation"),
            )

        latest = float(sahm.iloc[-1])
        if latest >= self.threshold_recession_pp:
            classification = "RECESSION_TRIGGERED"
        elif latest >= self.threshold_early_warning_pp:
            classification = "EARLY_WARNING"
        else:
            classification = "NORMAL"

        meta: dict[str, Any] = with_i18n({
            "source": self.source,
            "series_id": self.series_id,
            "n_obs": int(sahm.size),
            "first_date": str(sahm.index.min()),
            "last_date": str(sahm.index.max()),
            "latest_sahm_pp": latest,
            "latest_unrate_pct": float(unrate.iloc[-1]),
            "latest_3m_avg_pct": float(three_m_avg.iloc[-1]),
            "latest_12m_min_pct": float(twelve_m_min.iloc[-1]),
            "classification": classification,
            "thresholds_pp": {
                "recession": self.threshold_recession_pp,
                "early_warning": self.threshold_early_warning_pp,
            },
            "interpretation": (
                "Sahm Rule: 3-month avg of UNRATE minus its trailing "
                "12-month minimum, in percentage points. "
                ">= 0.50 pp = RECESSION_TRIGGERED (historical perfect record); "
                ">= 0.30 pp = EARLY_WARNING."
            ),
        }, "sahm_rule.interpretation")
        return IndicatorResult(
            indicator_id=self.id,
            version=self.version,
            values=sahm,
            metadata=meta,
        )
