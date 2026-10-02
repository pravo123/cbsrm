"""Branch alerts using the contract's illustrative, configurable thresholds."""
from __future__ import annotations

import pandas as pd

from cbsrm.mfi.config import DEFAULT_CONFIG
from cbsrm.mfi.migration import migration_matrix, roll_rates
from cbsrm.mfi.portfolio import portfolio_metrics


def branch_alerts(
    loans: pd.DataFrame, as_of: str, prev_as_of: str, config: dict | None = None,
) -> pd.DataFrame:
    """Evaluate the four rules, omitting NaNs; sort by branch_id, then rule.

    Evaluate branches present at either date using each branch's own rows.
    Missing metric snapshots are NaN and do not fire metric-change alerts.
    """
    thresholds = {**DEFAULT_CONFIG["alerts"], **(config or {}).get("alerts", {})}
    current = portfolio_metrics(loans, as_of, by=("branch_id",), config=config).set_index("branch_id")
    previous = portfolio_metrics(loans, prev_as_of, by=("branch_id",), config=config).set_index("branch_id")
    branches = current.index.union(previous.index).sort_values()
    current = current.reindex(branches)
    previous = previous.reindex(branches)
    alerts: list[dict] = []
    for branch in branches:
        branch_loans = loans.loc[loans["branch_id"] == branch]
        current_roll = roll_rates(migration_matrix(branch_loans, prev_as_of, as_of))["current"]
        values = {
            "PAR30_LEVEL": (current.loc[branch, "par30"], thresholds["par30_level"]),
            "PAR30_JUMP": (
                current.loc[branch, "par30"] - previous.loc[branch, "par30"],
                thresholds["par30_jump"],
            ),
            "ROLL_RATE": (current_roll, thresholds["roll_rate"]),
            "COLLECTION_DROP": (
                previous.loc[branch, "collection_efficiency"] - current.loc[branch, "collection_efficiency"],
                thresholds["collection_drop"],
            ),
        }
        for rule, (value, threshold) in values.items():
            if pd.notna(value) and value >= threshold:
                alerts.append({
                    "branch_id": branch,
                    "rule": rule,
                    "value": float(value),
                    "threshold": float(threshold),
                    "severity": "high" if value >= 2 * threshold else "medium",
                })
    return pd.DataFrame(
        alerts, columns=["branch_id", "rule", "value", "threshold", "severity"],
    ).sort_values(["branch_id", "rule"]).reset_index(drop=True)
