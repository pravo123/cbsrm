# Changelog

All notable changes to CBSRM are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and CBSRM adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.3
- SRISK (Brownlees-Engle 2017) on top of `bashtage/arch`
- LRMES + MES
- BIS Stats API adapter
- 2008Q4 / 2020Q1 / 2023Q1 crisis-replay notebooks

### Planned for v0.4
- ΔCoVaR (Adrian-Brunnermeier 2016)
- Acemoglu phase classifier
- `marcobardoscia/neva` network-contagion integration
- CFTC Public Reporting adapter

### Planned for v0.5
- Diebold-Yilmaz spillover index (Python reimplementation; existing R-only)
- Cross-jurisdiction integrator (the unique contribution)
- Streamlit dashboard

---

## [0.2.0] — 2026-05-21

### Added — v0.2 milestone: cross-source replication

**L1 — Data adapters**
- `cbsrm.data.ofr.OFRClient` — OFR Financial Stress Index (CSV) +
  Short-Term Funding Monitor (JSON) client. File-cached, retry-on-transient.
  Permissive CSV schema autodetection (column rename tolerant).
- `cbsrm.data.ecb_sdmx.ECBSDMXClient` — ECB Data Portal SDMX client in
  CSV mode (no XML SDMX deps). Convenience methods: `get_ciss_euro_area`,
  `get_ciss_us`, `get_ciss_uk`. Configurable base URL via env var.

**L2 — New indicator wrappers**
- `cbsrm.indicators.ofr_fsi.OFRFSIWrap` — passthrough indicator for the
  OFR FSI composite + 5-subindex breakdown (credit, equity valuation,
  funding, safe assets, volatility). Permissive column resolution.
- `cbsrm.indicators.ecb_ciss.ECBCISSWrap` — passthrough indicator for
  ECB-published CISS series. Supports euro-area (EA), US, UK variants.

**New subpackage — Diagnostics**
- `cbsrm.diagnostics.replication.replicate()` — cross-indicator comparison.
  Computes Pearson r, Spearman ρ, z-scored MAE over full sample plus
  declared crisis windows. Threshold-checking via
  `ReplicationReport.meets_threshold(full_sample_r, crisis_r)`.
- `cbsrm.diagnostics.replication.CRISIS_WINDOWS` — 9 canonical episodes
  (2007 subprime, 2008 GFC acute, 2010 EU debt, 2011 EU debt #2, 2015
  China deval, 2018Q4, 2020 COVID, 2022 inflation, 2023 SVB).

**CLI**
- `cbsrm ofr-fsi [-v]` — fetch + print latest OFR FSI composite.
- `cbsrm ecb-ciss [--variant EA|US|UK]` — fetch + print latest ECB CISS.
- `cbsrm replicate ciss-us ofr-fsi [--threshold-full 0.80 --threshold-crisis 0.75]`
  — run full replication diagnostics with PASS/FAIL against thresholds.
  Supports `ofr-fsi`, `ecb-ciss-ea`, `ecb-ciss-us`, `ecb-ciss-uk` as canonical side.
- `cbsrm info` updated to enumerate new indicators + data sources.

**Tests**
- 148 passing (was 91; +57 new). HTTP mocked, no live network needed.
- Test coverage: OFR client (13), OFR FSI wrapper (10), ECB client + CISS wrapper (18),
  replication diagnostics (15).

### Whitepaper §7.2 status

The v0.2 release satisfies the §7.2 commitment of cross-indicator replication.
`cbsrm replicate ciss-us ofr-fsi --start 2010-01-01` is the reference invocation.
Replication thresholds in v0.2: full-sample Pearson r ≥ 0.80, crisis-window Pearson r ≥ 0.75
(provisional; tightened to 0.85 / 0.80 in v0.3 after live-data validation).

---

## [0.1.0] — 2026-05-21

### Added

**L0 — Audit chain**
- `cbsrm.audit.chain.AuditChain` — sha256-linked append-only audit log
  with full lifecycle tracking (REQUESTED, INPUT_FETCHED, INPUT_MISSING,
  COMPUTED, SERVED, METHOD_UPGRADED, REPRODUCED, FAILED). Ported from
  the same author's production Derivatives Risk Framework.
- `cbsrm.audit.audited_indicator.AuditedIndicator` — thin wrapper that
  writes a full 4-event lifecycle on every `indicator.compute()` call,
  attaching the COMPUTED row id to the returned IndicatorResult.

**L1 — Public data ingestion**
- `cbsrm.data.fred.FREDClient` — Federal Reserve Economic Data API
  wrapper with file-cache, retry-on-transient, license-aware metadata
  accessor, and pandas Series/DataFrame outputs in UTC-tz timezone.

**L2 — Indicators (methodology)**
- `cbsrm.indicators.base.IIndicator` — protocol every indicator implements.
- `cbsrm.indicators.stlfsi.STLFSIWrap` — STLFSI4 passthrough as the
  baseline integrity check.
- `cbsrm.indicators.ciss_us.CISSUS` — Composite Indicator of Systemic
  Stress (Holló-Kremer-Lo Duca 2012) applied to US data with
  user-configurable input mapping.
- `cbsrm.indicators.ciss_us_canonical.CISSUSCanonical` — CISSUS with
  the frozen canonical FRED-derived input mapping (15 inputs across
  5 subindices: money market, bond market, equity market, financial
  intermediaries, foreign exchange).

**Builders**
- `cbsrm.builders.ciss_us_builder.CISSUSBuilder` — bridge from raw FRED
  series to CISSUS-ready 15-column input matrix. Implements recipes for
  SPREAD, ABS, CMAX, REALVOL, DAILY_VOL transforms. Returns reproducibility
  manifest documenting every input's source and substitution status.

**L5 — API + CLI**
- `cbsrm.api.routes.build_app` — FastAPI service exposing indicator
  registry, audit-chain access, and chain verification.
- `cbsrm` CLI with subcommands: `info`, `latest`, `ciss-us`, `verify-audit`.

**Documentation**
- `README.md` with architecture diagram, quick-start, citation form.
- `whitepaper/cbsrm_methodology_v1.md` — 10-section academic-style paper
  (~5,800 words) covering methodology, related work, BIS Innovation Hub
  alignment, replication strategy, and limitations.
- `examples/run_ciss_us.py` — end-to-end demo script.

**Testing**
- 91 tests, all passing on Python 3.10+.
- Test coverage spans audit chain integrity, FRED HTTP mocking, indicator
  protocol conformance, CISS-US synthetic crisis-window validation,
  builder recipe correctness, and audited-indicator lifecycle.

**Infrastructure**
- `pyproject.toml` configured for PyPI publication.
- Apache 2.0 license.
- GitHub Actions CI matrix (Ubuntu/macOS/Windows × Python 3.10/3.11/3.12).

### Notes
- BIS Stats API and ECB Data Portal adapters are scaffolded in the
  `cbsrm.data.__init__` module docstring but ship in v0.2.
- The CISS-US canonical 15-input mapping documented in the whitepaper §3.2
  includes several substitutes for inputs not available on FRED (e.g.
  basis swaps, SLOOS diffusion). The builder's manifest records every
  substitution; the v0.2 release will reduce substitutions by adding
  the ECB SDMX adapter for euro-area cross-references.
