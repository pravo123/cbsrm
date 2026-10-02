"""Transitions weighted by opening exposure (or opening loan count)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cbsrm.mfi.config import BUCKETS, assign_bucket

STATES = BUCKETS + ["written_off", "closed"]


def migration_matrix(
    loans: pd.DataFrame, from_as_of: str, to_as_of: str, weight: str = "outstanding",
) -> pd.DataFrame:
    """Return opening live-bucket shares across STATES; zero-weight rows are NaN.

    Missing destination loans are closed. New loans and opening writeoffs do
    not participate. Destination writeoffs take precedence over their DPD.
    """
    if weight not in ("outstanding", "count"):
        raise ValueError("weight must be 'outstanding' or 'count'")
    start = loans.loc[
        (loans["as_of"] == from_as_of) & (loans["written_off"] == 0),
        ["loan_id", "days_past_due", "outstanding_npr"],
    ].copy()
    end = loans.loc[loans["as_of"] == to_as_of, ["loan_id", "days_past_due", "written_off"]].copy()
    start["from_bucket"] = assign_bucket(start["days_past_due"])
    start["weight"] = 1.0 if weight == "count" else start["outstanding_npr"].astype(float)
    end["to_state"] = assign_bucket(end["days_past_due"]).astype(object)
    end.loc[end["written_off"] == 1, "to_state"] = "written_off"
    moves = start.merge(end[["loan_id", "to_state"]], on="loan_id", how="left")
    moves["to_state"] = moves["to_state"].fillna("closed")
    matrix = moves.pivot_table(
        index="from_bucket", columns="to_state", values="weight",
        aggfunc="sum", fill_value=0.0, observed=True,
    ).reindex(index=BUCKETS, columns=STATES, fill_value=0.0).astype(float)
    matrix = matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0)
    return matrix.rename_axis(index=None, columns=None)


def roll_rates(matrix: pd.DataFrame) -> pd.Series:
    """Share moving to worse buckets or written_off; closed never counts as worse."""
    return pd.Series({
        bucket: float(matrix.loc[bucket, [*BUCKETS[i + 1:], "written_off"]].sum(min_count=1))
        for i, bucket in enumerate(BUCKETS)
    }, dtype=float)
