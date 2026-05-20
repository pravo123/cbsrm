"""
CISSUSCanonical — CISSUS with the frozen canonical subindex mapping.

The base CISSUS class accepts any user-supplied 15-column DataFrame; this
subclass freezes the canonical FRED-mapping subindex assignment so that
results computed with it are reproducible across runs and across users.

The actual mapping of subindex → column names matches the names emitted
by cbsrm.builders.ciss_us_builder.CANONICAL_SPECS.
"""
from __future__ import annotations

from cbsrm.indicators.ciss_us import CISSConfig, CISSUS, SUBINDEX_NAMES


CANONICAL_INPUTS_BY_SUBINDEX: dict[str, tuple[str, ...]] = {
    "money_market":             ("money_market_1", "money_market_2", "money_market_3"),
    "bond_market":              ("bond_market_1", "bond_market_2", "bond_market_3"),
    "equity_market":            ("equity_market_1", "equity_market_2", "equity_market_3"),
    "financial_intermediaries": ("financial_intermediaries_1",
                                  "financial_intermediaries_2",
                                  "financial_intermediaries_3"),
    "fx_market":                ("fx_market_1", "fx_market_2", "fx_market_3"),
}

# Sanity check: every canonical subindex matches the SUBINDEX_NAMES tuple
assert set(CANONICAL_INPUTS_BY_SUBINDEX.keys()) == set(SUBINDEX_NAMES), (
    "canonical subindex names drifted from cbsrm.indicators.ciss_us.SUBINDEX_NAMES"
)


class CISSUSCanonical(CISSUS):
    """CISSUS with the frozen canonical FRED-derived input mapping.

    Use this class when you want results that match the published CBSRM
    methodology exactly. Use the base CISSUS class for custom mappings.
    """

    id: str = "CISS-US-Canonical"
    version: str = "0.1.0"
    source: str = (
        "Methodology: Holló, Kremer, Lo Duca (2012), 'CISS', ECB WP 1426. "
        "US extension with frozen FRED-derived input mapping: "
        "CBSRM v0.1, https://github.com/pravo123/cbsrm."
    )

    def __init__(self, ewma_lambda: float = 0.93,
                 weights: tuple[float, ...] = (0.2, 0.2, 0.2, 0.2, 0.2)) -> None:
        super().__init__(CISSConfig(
            ewma_lambda=ewma_lambda,
            weights=weights,
            inputs_by_subindex=CANONICAL_INPUTS_BY_SUBINDEX,
        ))
