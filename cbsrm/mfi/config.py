"""Frozen v1 defaults: illustrative, to be calibrated to current NRB directives.

These synthetic-demo thresholds, buckets and rates make no compliance claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_CONFIG: dict = {
    "npl_dpd_threshold": 90,
    "provision_rates": {
        "current": 0.01,
        "b1_30": 0.05,
        "b31_90": 0.25,
        "b91_180": 0.50,
        "b180p": 1.00,
    },
    "alerts": {
        "par30_level": 0.10,
        "par30_jump": 0.02,
        "roll_rate": 0.05,
        "collection_drop": 0.05,
    },
}

BUCKETS: list[str] = ["current", "b1_30", "b31_90", "b91_180", "b180p"]


def assign_bucket(days_past_due: pd.Series) -> pd.Series:
    """Assign the contract's ordered, illustrative DPD buckets to live loans."""
    return pd.cut(days_past_due, bins=[-1, 0, 30, 90, 180, np.inf], labels=BUCKETS)
