"""Simultaneous one-bucket stress and balance-sheet impacts, frozen contract v1."""
from __future__ import annotations

import pandas as pd

from cbsrm.mfi.config import BUCKETS, DEFAULT_CONFIG


def apply_scenario(
    segments: pd.DataFrame, balance_sheet: dict, scenario: dict, config: dict | None = None,
) -> dict:
    """Apply segment multipliers and return unrounded contract outputs.

    Bucket migration uses pre-shock balances; b180p retains its balance.
    Provision rates are illustrative, to be calibrated to current NRB directives.
    """
    rates = {**DEFAULT_CONFIG["provision_rates"], **(config or {}).get("provision_rates", {})}
    sector_mult = segments["sector"].map(scenario.get("sector_mult", {})).fillna(1.0)
    province_mult = segments["province"].map(scenario.get("province_mult", {})).fillna(1.0)
    shift = (scenario.get("base_shift", 0.0) * sector_mult * province_mult).clip(upper=1.0)
    before = segments[BUCKETS]
    after = before.mul(1.0 - shift, axis=0)
    after["b180p"] = before["b180p"]
    for i in range(1, len(BUCKETS)):
        after[BUCKETS[i]] += before[BUCKETS[i - 1]] * shift
    totals = {bucket: float(after[bucket].sum()) for bucket in BUCKETS}
    gross = sum(totals.values())
    provisions = sum(totals[bucket] * rates[bucket] for bucket in BUCKETS)
    base_provisions = sum(float(before[bucket].sum()) * rates[bucket] for bucket in BUCKETS)
    delta_provisions = provisions - base_provisions
    nii_hit = balance_sheet["borrowings_npr"] * scenario.get("funding_cost_bps", 0) / 10000
    capital = balance_sheet["capital_npr"] - delta_provisions - nii_hit
    rwa = balance_sheet["rwa_npr"]
    liquidity_gap = (
        balance_sheet["liquid_assets_npr"]
        + balance_sheet["inflows_90d_npr"] * (1 - scenario.get("inflow_haircut", 0.0))
        - balance_sheet["outflows_90d_npr"] * scenario.get("outflow_mult", 1.0)
    )
    return {
        "scenario_id": scenario["id"],
        "buckets": totals,
        "gross_npr": gross,
        "par30": (totals["b31_90"] + totals["b91_180"] + totals["b180p"]) / gross if gross else float("nan"),
        "par90": (totals["b91_180"] + totals["b180p"]) / gross if gross else float("nan"),
        "provisions_npr": provisions,
        "delta_provisions_npr": delta_provisions,
        "nii_hit_npr": nii_hit,
        "capital_npr": capital,
        "car": capital / rwa if rwa else float("nan"),
        "liquidity_gap_90d_npr": liquidity_gap,
    }
