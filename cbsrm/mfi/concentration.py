"""Concentration of live outstanding principal, on the zero-to-one scale."""
from __future__ import annotations

import pandas as pd


def hhi(loans: pd.DataFrame, as_of: str, by: str) -> float:
    """Sum squared group shares of gross NPR; return NaN for zero gross."""
    live = loans.loc[(loans["as_of"] == as_of) & (loans["written_off"] == 0)]
    balances = live.groupby(by, observed=True)["outstanding_npr"].sum()
    gross = float(balances.sum())
    return float(((balances / gross) ** 2).sum()) if gross else float("nan")


def top_n_share(loans: pd.DataFrame, as_of: str, by: str, n: int = 5) -> float:
    """Share of live gross NPR in the n largest groups; NaN for zero gross."""
    live = loans.loc[(loans["as_of"] == as_of) & (loans["written_off"] == 0)]
    balances = live.groupby(by, observed=True)["outstanding_npr"].sum()
    gross = float(balances.sum())
    return float(balances.nlargest(n).sum() / gross) if gross else float("nan")
