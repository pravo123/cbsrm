"""Pure month-end portfolio metrics for the frozen Laghubitta contract."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from cbsrm.mfi.config import BUCKETS, DEFAULT_CONFIG, assign_bucket


def portfolio_metrics(
    loans: pd.DataFrame,
    as_of: str,
    by: Sequence[str] = (),
    config: dict | None = None,
) -> pd.DataFrame:
    """Return contract metrics, sorted by grouping columns; no groups means one row.

    Exposure ratios use live loans. Writeoffs and collections use all rows.
    Zero denominators produce NaN. Config keys override illustrative defaults.
    """
    npl_threshold = (config or {}).get("npl_dpd_threshold", DEFAULT_CONFIG["npl_dpd_threshold"])
    frame = loans.loc[loans["as_of"] == as_of].copy()
    live = frame["written_off"] == 0
    outstanding = frame["outstanding_npr"].where(live, 0.0)
    frame["gross_npr"] = outstanding
    frame["par30"] = outstanding.where(frame["days_past_due"] > 30, 0.0)
    frame["par90"] = outstanding.where(frame["days_past_due"] > 90, 0.0)
    frame["npl_ratio"] = outstanding.where(frame["days_past_due"] > npl_threshold, 0.0)
    frame["restructured_ratio"] = outstanding.where(frame["restructured"] == 1, 0.0)
    frame["n_loans"] = live.astype(int)
    sums = [
        "gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
        "writeoff_npr", "due_npr", "collected_npr", "n_loans",
    ]
    if by:
        result = frame.groupby(list(by), sort=True, observed=True)[sums].sum().reset_index()
    else:
        result = frame[sums].sum().to_frame().T
    gross = result["gross_npr"].replace(0, np.nan)
    for column in ("par30", "par90", "npl_ratio", "restructured_ratio"):
        result[column] = result[column] / gross
    result["writeoff_ratio"] = result["writeoff_npr"] / (
        result["gross_npr"] + result["writeoff_npr"]
    ).replace(0, np.nan)
    result["collection_efficiency"] = result["collected_npr"] / result["due_npr"].replace(0, np.nan)
    result["n_loans"] = result["n_loans"].astype(int)
    return result[[
        *by, "gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
        "writeoff_ratio", "collection_efficiency", "n_loans",
    ]]


def bucket_balances(
    loans: pd.DataFrame, as_of: str, by: Sequence[str] = (),
) -> pd.DataFrame:
    """Return live NPR balances in BUCKETS order, sorted by grouping columns."""
    frame = loans.loc[(loans["as_of"] == as_of) & (loans["written_off"] == 0)].copy()
    buckets = assign_bucket(frame["days_past_due"])
    for bucket in BUCKETS:
        frame[bucket] = frame["outstanding_npr"].where(buckets == bucket, 0.0)
    if by:
        return frame.groupby(list(by), sort=True, observed=True)[BUCKETS].sum().reset_index()
    return frame[BUCKETS].sum().to_frame().T
