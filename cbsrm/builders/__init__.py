"""
cbsrm.builders — turn raw upstream series into indicator-ready input matrices.

Each builder takes one or more data clients (FRED, ECB, etc.), pulls the
underlying series, applies derived transformations (spreads, CMAX, realized
vol), and returns the canonical N-column DataFrame the corresponding
indicator expects.

Builders are kept SEPARATE from indicators so that:
  - The indicator class stays methodology-only (no upstream dependency)
  - Users can swap a different builder if they have alternative data
  - Replication notebooks can construct inputs by hand and feed them
    directly to the indicator, bypassing the builder

Currently implemented:
  - CISSUSBuilder — FRED → 15-column matrix for CISSUS

Planned:
  - CISSEurBuilder      — ECB SDMX → 15-column matrix for euro-area replication
  - SRISKBuilder        — equity prices + balance sheets → SRISK inputs
  - SpilloverBuilder    — multi-asset returns → DY spillover inputs
"""
from cbsrm.builders.ciss_us_builder import (
    CISSUSBuilder, CISSUSBuilderManifest, CISSUSBuilderConfig,
)

__all__ = [
    "CISSUSBuilder",
    "CISSUSBuilderManifest",
    "CISSUSBuilderConfig",
]
