# Contributing to CBSRM

CBSRM is open-source quantitative infrastructure for cross-jurisdiction systemic-risk monitoring. The repository accepts contributions in three categories:

1. **Methodology** — new indicators, network models, or improvements to the existing CISS-US / SRISK / CoVaR / spillover implementations.
2. **Data** — new public data adapters (BIS, ECB, IMF, NY Fed, OFR, World Bank, CFTC, etc.).
3. **Infrastructure** — performance improvements, additional tests, dashboard work, audit-chain export formats, API endpoints.

## Ground rules

### Reproducibility is non-negotiable

Every numerical claim in the codebase must be reproducible from public inputs. Pull requests that introduce indicators relying on private data feeds, paywalled APIs without a free tier, or hardcoded data dumps will be rejected. The point of CBSRM is that any researcher can clone the repo, set their FRED key (free), and replicate every value end-to-end.

### Methodology citations are mandatory

Every new indicator class must reference at least one peer-reviewed paper or central-bank working paper in its module-level docstring and in its `.source` attribute. We do not accept "vibes-based" indicators.

### Audit chain coverage

Any new indicator should compose cleanly with `cbsrm.audit.AuditedIndicator`. If a new compute path bypasses the audit chain, justify why in the PR description.

### Tests

- All new modules require unit tests in `tests/`.
- The full test suite must pass on Python 3.10, 3.11, and 3.12.
- Tests should not require network access (mock HTTP for data adapters).
- Methodology tests should include at least one synthetic crisis-regime validation.

### License posture for data

Adapters wrapping a new data source must:
- Document the license in the module docstring.
- Expose source attribution via a `source_info()` method on the client class.
- Treat BIS, ECB, and similarly-licensed sources as inputs to derived analytics, not raw redistribution.

## Local development

```bash
git clone https://github.com/pravo123/cbsrm
cd cbsrm
pip install -e ".[all]"
pytest tests/ -v
```

## Pull request checklist

- [ ] Methodology cites a paper or working paper
- [ ] Module-level docstring explains what, why, citations
- [ ] Unit tests added; full suite passes
- [ ] CHANGELOG.md updated under [Unreleased]
- [ ] No new private data dependencies
- [ ] Audit-chain compatibility documented if applicable

## What is out of scope

CBSRM is **not** a backtesting framework, a portfolio-optimizer, or a trading-signal generator. We focus exclusively on systemic-stress measurement, network contagion, and supervisory technology primitives. Adjacent work (portfolio construction, alpha factors, etc.) should live in companion repositories.

CBSRM is also **not** a wrapper layer for proprietary data sources. We integrate public APIs only. Paid value-add (real-time feeds, custom institution lists) lives in the planned commercial tier, not in the OSS distribution.

## Correspondence

Researchers at BIS, ECB, OFR, NY Fed, Fed Board, IMF, FSB, ESRB, and equivalent institutions are particularly welcome to open issues. Code-review feedback from central-bank-adjacent researchers carries extra weight in the project's roadmap prioritization.
