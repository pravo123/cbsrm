# CBSRM — Cross-Border Systemic Risk Monitor

> Open-source quantitative framework for cross-jurisdiction financial-stability monitoring.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Whitepaper](https://img.shields.io/badge/whitepaper-v0.1-green.svg)](whitepaper/cbsrm_methodology_v1.md)

CBSRM reproduces and extends the canonical systemic-risk indices used by central banks (ECB CISS, OFR FSI, NYU V-Lab SRISK, Adrian-Brunnermeier CoVaR) in modern typed Python, integrates them across jurisdictions (US, EU, UK, Japan, EM), and exposes the result via a public API. Every value is computed with a regulator-grade tamper-evident audit chain.

## Why this exists

The public landscape of systemic-stress indicators is fragmented by geography:

| Source | Coverage | Cadence | Methodology open? | API? |
|---|---|---|---|---|
| NYU V-Lab (SRISK) | US large banks | Weekly | Partial | No |
| ECB CISS | Euro area | Weekly | Yes (WP 1426) | Yes |
| OFR FSI | US | Daily | Yes (Risks 2019) | No |
| KC Fed FSI | US | Monthly | Yes | Via FRED |
| Chicago Fed NFCI | US | Weekly | Yes | Via FRED |
| **CBSRM** | **Multi-jurisdiction** | **Daily** | **Yes** | **Yes** |

**The gap CBSRM fills:** no single public artifact aggregates these methodologies across jurisdictions with attribution, transparent code, and an API.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1  PUBLIC DATA INGESTION                                            │
│     FRED · NY Fed · OFR STFM · ECB · BIS · CFTC                      │
├──────────────────────────────────────────────────────────────────────┤
│ L2  INDICATORS LAYER (methodology IP)                                │
│     STLFSI · CISS-US · CISS-EM · SRISK · CoVaR · DY-spillover        │
├──────────────────────────────────────────────────────────────────────┤
│ L3  NETWORK / CONTAGION LAYER                                        │
│     neva (Eisenberg-Noe, DebtRank) · Glasserman-Young bounds         │
├──────────────────────────────────────────────────────────────────────┤
│ L4  CROSS-JURISDICTION INTEGRATOR  (the unique contribution)         │
│     Fuses L2+L3 across US/EU/UK/JP/EM with source attribution        │
├──────────────────────────────────────────────────────────────────────┤
│ L5  PUBLIC API + DASHBOARD                                           │
│     FastAPI · OpenAPI · OSS tier (rate-limited)                      │
├──────────────────────────────────────────────────────────────────────┤
│ L0  AUDIT CHAIN  (under everything)                                  │
│     sha256-chained tamper-evident log of every computation           │
└──────────────────────────────────────────────────────────────────────┘
```

## Current status (v0.1)

| Layer | Module | Status |
|---|---|---|
| L0 | `cbsrm.audit.chain.AuditChain` | ✅ shipped |
| L1 | `cbsrm.data.fred.FREDClient` | ✅ shipped |
| L2 | `cbsrm.indicators.stlfsi.STLFSIWrap` | ✅ shipped (baseline) |
| L2 | `cbsrm.indicators.ciss_us.CISSUS` | ✅ shipped (methodology) |
| L2 | SRISK, CoVaR, DY-spillover | planned (v0.2-v0.4) |
| L3 | neva integration | planned (v0.3) |
| L4 | Cross-jurisdiction integrator | planned (v0.5) |
| L5 | `cbsrm.api.routes` FastAPI | ✅ shipped (skeleton) |
| CLI | `cbsrm latest STLFSI4` | ✅ shipped |

**48 tests passing**, methodology replicates against synthetic crisis windows.

## Quick start

```bash
git clone https://github.com/pravo123/cbsrm
cd cbsrm
pip install -e ".[all]"
```

### CLI: latest stress reading

```bash
export FRED_API_KEY=your_free_fred_key
cbsrm latest STLFSI4
```

```json
{
  "indicator_id": "STLFSI4",
  "version": "1.0.0",
  "as_of": "2026-05-15T00:00:00+00:00",
  "value": -0.18,
  "interpretation": "0 = normal conditions; >0 above-average stress; <0 below-average. Weekly-Thursday cadence."
}
```

### Python: compute CISS-US

```python
from cbsrm.data import FREDClient
from cbsrm.indicators import CISSUS
from cbsrm.indicators.ciss_us import CISSConfig

# Wire FRED mnemonics to CISS subindices (US extension; see whitepaper §3.2)
config = CISSConfig(
    inputs_by_subindex={
        "money_market":            ("TEDRATE", "SOFR_IORB_SPREAD", "CP_TBILL_SPREAD"),
        "bond_market":             ("T10Y2Y_ABS", "BAMLH0A0HYM2", "MOVE_PROXY"),
        "equity_market":           ("VIXCLS", "SPX_CMAX", "SPX_FIN_BETA"),
        "financial_intermediaries":("KBW_CMAX", "BANK_REALVOL", "SLOOS_TIGHTENING"),
        "fx_market":               ("DXY_VOL", "EURUSD_BASIS", "JPYUSD_BASIS"),
    }
)
indicator = CISSUS(config)

# Operator constructs the 15-column input frame from FRED (see notebooks/)
# df = build_ciss_inputs_from_fred(FREDClient(api_key="..."))

result = indicator.compute(df)
print(result.latest)           # (timestamp, 0.42)
print(result.subindex_values)  # per-segment breakdown
```

### API server

```bash
pip install cbsrm[api]
uvicorn cbsrm.api.routes:app --reload
# → http://127.0.0.1:8000/docs
```

```
GET  /                                — service info
GET  /indicators                      — list registered indicators
GET  /indicators/{id}/latest          — latest reading
GET  /audit/{subject}                 — audit chain for a subject
POST /audit/verify                    — verify chain integrity
```

### Regulator-grade audit

Every CBSRM indicator value carries an audit row id. The audit chain is sha256-linked: any tampering breaks the chain and is detectable in O(n).

```python
from cbsrm.audit import AuditChain, AuditEvent, AuditEventKind
import sqlite3

conn = sqlite3.connect("cbsrm_audit.db")
audit = AuditChain(conn)

audit.append(AuditEvent(AuditEventKind.REQUESTED,    "CISS-US"))
audit.append(AuditEvent(AuditEventKind.INPUT_FETCHED,"CISS-US", {"n_series": 15}))
audit.append(AuditEvent(AuditEventKind.COMPUTED,     "CISS-US", {"value": 0.42}))
audit.append(AuditEvent(AuditEventKind.SERVED,       "CISS-US", {"to": "api"}))

ok, broken = audit.verify()
assert ok            # True iff no tampering since first append
```

## Whitepaper

The full methodology, replication strategy, and BIS-context positioning is in [whitepaper/cbsrm_methodology_v1.md](whitepaper/cbsrm_methodology_v1.md).

The paper covers:
- §1 Introduction and motivation
- §2 Related work (V-Lab, CISS, OFR FSI, BIS WPs 1250/1291)
- §3 Methodology (CISS-US construction, SRISK replication strategy)
- §4 Data sources and license posture
- §5 Architecture and audit-chain design
- §6 Programmable risk-gate extension (bridge to Project Pine)
- §7 Replication diagnostics (synthetic crisis windows)
- §8 Cross-jurisdiction integration roadmap
- §9 Limitations and threat model
- §10 BIS Innovation Hub alignment

## License

Apache 2.0 — full text in [LICENSE](LICENSE). Derived analytics on FRED/NY Fed/OFR/CFTC data are unrestricted commercial use; ECB and BIS underlying series have additional attribution requirements (the code automatically surfaces source metadata via `.source_info()` on each adapter).

## Citation

If you use CBSRM in research or product:

```bibtex
@software{cbsrm2026,
  author  = {WaverVanir International LLC},
  title   = {CBSRM: Cross-Border Systemic Risk Monitor},
  version = {0.1.0},
  year    = {2026},
  url     = {https://github.com/pravo123/cbsrm},
}
```

## Related work from the same author

- [Derivatives Risk Framework (DRF)](https://github.com/pravo123/derivatives-risk-framework) — Apache-2.0 production-grade derivatives risk + audit infrastructure (private capital deployment). CBSRM lifts the audit-chain primitive from DRF and applies it to public systemic-stress computations.
