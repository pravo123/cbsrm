"""
cbsrm.networks — financial-network systemic-risk primitives.

Pure-numpy implementations of network-contagion measures over interbank
exposure graphs. Pairs with the v0.7 Diebold-Yilmaz spillover indicator
(``cbsrm.indicators.dy_spillover``) on the market-return side.

Inventory
---------

- ``debt_rank`` — Battiston, Puliga, Kaushik, Tasca, Caldarelli (2012)
  DebtRank centrality. State-machine cascade on a leverage-normalized
  exposure matrix.
- ``build_contagion_elements`` — turns a DebtRank cascade into
  node/edge + Cytoscape.js elements with per-node color states for an
  interactive contagion visualization.
"""
from cbsrm.networks.contagion_elements import (
    CONTAGION_ELEMENTS_VERSION,
    build_contagion_elements,
)
from cbsrm.networks.debt_rank import debt_rank

__all__ = [
    "debt_rank",
    "build_contagion_elements",
    "CONTAGION_ELEMENTS_VERSION",
]
