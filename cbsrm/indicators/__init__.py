"""
cbsrm.indicators — systemic-stress methodology layer.

Each indicator is one Python class implementing the IIndicator protocol:
  - .id          — short identifier ("STLFSI4", "CISS-US", "SRISK", ...)
  - .version     — methodology version, append-only string
  - .source      — citation
  - .required_series() → list of FRED/ECB/BIS series ids
  - .compute(data) → pandas.Series of stress values

Currently implemented (v0.2):
  - STLFSIWrap       — FRED STLFSI4 passthrough (sanity baseline)
  - OFRFSIWrap       — OFR FSI passthrough (canonical US daily stress index)
  - ECBCISSWrap      — ECB CISS passthrough (canonical euro-area composite)
  - CISSUS           — CISS methodology (Holló-Kremer-Lo Duca 2012)
  - CISSUSCanonical  — CISSUS with frozen canonical FRED-derived input mapping

Planned (per whitepaper §3):
  - NFCIWrap, KCFSIWrap          — single-series wrappers
  - SRISK, MES, LRMES            — Brownlees-Engle 2017
  - CoVaR                         — Adrian-Brunnermeier 2016
  - DYSpillover                  — Diebold-Yilmaz 2012 / Barunik-Krehlik 2018
  - EWS                          — KLR + Manasse-Roubini + ML benchmark
"""
from cbsrm.indicators.base import IIndicator, IndicatorResult
from cbsrm.indicators.bis_cbs_claims import BISCBSClaimsIndicator
from cbsrm.indicators.bis_otc_derivatives import BISOTCDerivativesIndicator
from cbsrm.indicators.dy_spillover import (
    DYSpilloverIndicator, spillover_series,
)
from cbsrm.indicators.ciss_us import CISSConfig, CISSUS, SUBINDEX_NAMES
from cbsrm.indicators.ciss_us_canonical import (
    CANONICAL_INPUTS_BY_SUBINDEX, CISSUSCanonical,
)
from cbsrm.indicators.ecb_ciss import ECBCISSWrap, VARIANT_LABELS
from cbsrm.indicators.ofr_fsi import OFRFSIWrap
from cbsrm.indicators.stlfsi import STLFSIWrap

__all__ = [
    "IIndicator", "IndicatorResult",
    "STLFSIWrap", "OFRFSIWrap", "ECBCISSWrap", "VARIANT_LABELS",
    "CISSUS", "CISSConfig", "SUBINDEX_NAMES",
    "CISSUSCanonical", "CANONICAL_INPUTS_BY_SUBINDEX",
    "BISOTCDerivativesIndicator", "BISCBSClaimsIndicator",
    "DYSpilloverIndicator", "spillover_series",
]
