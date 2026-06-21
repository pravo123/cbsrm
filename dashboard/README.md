# CBSRM Dashboards

## ⭐ Flagship: CBSRM Risk Terminal (`cbsrm_terminal.html`)

A **self-contained, offline, single-file** institutional risk terminal — the
"Obsidian Ledger" — built for chief-risk-officer / supervisory audiences at
asset managers, insurers, and banks. Zero external dependencies (no CDN, no web
fonts, no JS libraries); every chart is hand-rolled inline SVG. Open the file
directly in any browser, or embed it anywhere via an `<iframe>`.

```bash
# (re)generate the audit-grade data bundle from the canonical cbsrm classes
python dashboard/build_terminal_data.py      # -> dashboard/cbsrm_terminal_data.json
# then just open the file — no server required
open dashboard/cbsrm_terminal.html           # or: python -m http.server -d dashboard
```

**What it shows** — six governance / systemic-risk-measurement lenses across the
three canonical crisis windows (2008Q4 / 2020Q1 / 2023Q1), switchable live:

| Lens | Measure | Methodology |
| --- | --- | --- |
| System Stress | phase-classifier score (CISS-family offline proxy) | Holló–Kremer–Lo Duca 2012 |
| Firm Capital Shortfall | SRISK waterfall, ΣSRISK⁺ | Brownlees–Engle 2017 |
| Tail Spillover | ΔCoVaR + MES | Adrian–Brunnermeier 2016 · Acharya et al. 2017 |
| Network Contagion | DebtRank cascade | Battiston et al. 2012 |
| Macro Regime | 4-state phase + Estrella–Mishkin probit | Estrella–Mishkin 1996 |
| Model Governance | SHA-256 audit hash-chain | SR 26-2 · NIST FIPS 180-4 |

**Provenance.** Every number is computed from the public `cbsrm` classes (the
same ones the CLI and FastAPI use) by `build_terminal_data.py`, which inlines
the result into the HTML. It is reproducible bit-for-bit and self-checks for
determinism on each run; the audit chain verifies (`chain_ok = true`). Crisis
fixtures are deterministic; the G-SIB balance sheets and the ΔCoVaR/MES pair are
clearly-labelled illustrative/synthetic. **Scope is risk measurement and model
governance only — no trade signals, positions, or P&L.** Apache-2.0; not
investment advice.

---

## Streamlit demos

A single-page Streamlit demo of the CBSRM public API (currently surfacing
v0.5 risk-pricing readings on top of v0.8.0). Renders the 4-state macro
regime, ECB CISS + STLFSI4 stress readings, yield-curve recession
probability, USD/JPY + DXY regimes, FFR change, SRISK for three illustrative
G-SIBs, and a synthetic-paired-return ΔCoVaR / MES illustration — all from the
installed `cbsrm` package.

For the v0.8 research-flow surfaces (macro event scorer, replay, DebtRank,
phase classifier, crisis dossiers, report renderer), see the standalone
offline page documented below ([Crisis Dossier Viewer (v0.8, offline)](#crisis-dossier-viewer-v08-offline))
or the programmatic interfaces in
[`../docs/v0.8_research_flow.md`](../docs/v0.8_research_flow.md).

## 5-second start

```bash
git clone https://github.com/pravo123/cbsrm
cd cbsrm
pip install -e ".[all]" streamlit
export FRED_API_KEY=your_free_fred_key   # https://fred.stlouisfed.org/docs/api/api_key.html
streamlit run dashboard/streamlit_app.py
```

The dashboard listens on `http://localhost:8501` by default and renders all
panels in under ~30 seconds on first load (cached on refresh).

## Screenshot

![dashboard screenshot](screenshot.png)

> If the screenshot is a placeholder, take one yourself: launch the dashboard
> as above, wait for it to render, then capture the browser viewport
> (`PrintScreen` / `Cmd+Shift+4`) into `dashboard/screenshot.png`.

## What this is — and isn't

**It is** a demo artifact: methodology preview, screenshot fodder, README eye
candy. Every number is computed from the same public CBSRM classes the CLI
uses; you can re-run any panel from `examples/quickstart.py` and get matching
results.

**It is not** production monitoring, an order-entry surface, an API, or
investment advice. The SRISK panel uses *approximate* market-cap and book-debt
figures for JPM, BAC, and C — clearly labeled as illustrative. For
regulator-grade live numbers, consult NYU Stern V-Lab.

## Crisis Dossier Viewer (v0.8, offline)

A second standalone Streamlit page lives at
[`crisis_dossier_viewer.py`](crisis_dossier_viewer.py). It renders the
deterministic v0.8 crisis-window dossiers (`2008Q4`, `2020Q1`, `2023Q1`)
through the canonical report renderer and offers Markdown / JSON downloads.
No FRED key, no network calls, no API server required.

```bash
pip install -e ".[all]" streamlit
streamlit run dashboard/crisis_dossier_viewer.py
```

Mirrors the CLI surface (`cbsrm crisis-dossier WINDOW --format ...`) and the
FastAPI surface (`GET /reports/crisis-dossiers/...`) bit-for-bit — all three
front-ends share the same `cbsrm.diagnostics.build_crisis_dossier` +
`cbsrm.reporting` payload/renderer composition.

## License

Apache 2.0. Same as the rest of CBSRM.
