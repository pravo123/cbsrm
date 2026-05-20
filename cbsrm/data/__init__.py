"""
cbsrm.data — public data ingestion layer.

Each module wraps one public data source with consistent semantics:
  - typed series identifiers
  - cached, rate-limited fetch
  - pandas.DataFrame outputs with UTC-tz datetime index
  - license metadata exposed via .source_info()

Currently implemented:
  - fred       — Federal Reserve Economic Data (St. Louis Fed)
  - ofr        — OFR Financial Stress Index (CSV) + Short-Term Funding Monitor (JSON)
  - ecb_sdmx   — ECB Data Portal (SDMX, CSV mode — no XML deps)

Planned (per cbsrm whitepaper §4):
  - nyfed       — NY Fed Markets API
  - bis_sdmx    — BIS Statistics API
  - cftc        — CFTC Public Reporting Environment
"""
from cbsrm.data.ecb_sdmx import (
    ECB_CISS_EURO_AREA, ECB_CISS_FLOWREF, ECB_CISS_UK, ECB_CISS_US,
    ECBSDMXClient, ECBSDMXMeta,
)
from cbsrm.data.fred import FREDClient, FREDSeriesMeta
from cbsrm.data.ofr import OFRClient, OFRFSIMeta

__all__ = [
    "FREDClient", "FREDSeriesMeta",
    "OFRClient", "OFRFSIMeta",
    "ECBSDMXClient", "ECBSDMXMeta",
    "ECB_CISS_EURO_AREA", "ECB_CISS_US", "ECB_CISS_UK", "ECB_CISS_FLOWREF",
]
