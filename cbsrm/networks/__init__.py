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
"""
from cbsrm.networks.debt_rank import debt_rank

__all__ = ["debt_rank"]
