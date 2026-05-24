# SSRN submission package — CBSRM methodology paper

This file holds everything required to submit the CBSRM v0.5 methodology paper to SSRN. Copy each field to the corresponding form input.

> **State as of `v0.8.0` release (tag `v0.8.0`, commit `410e3ac`):**
> The methodology paper itself was drafted for the v0.5 risk-pricing release; the v0.8 work (macro-event surprise scorer, windowed replay, pure-numpy DebtRank, Acemoglu-style phase classifier, fixture-backed crisis-window dossiers, deterministic report renderer, plus CLI / FastAPI / Streamlit front-ends) extends the same Protocol-based architecture without modifying the v0.5 surface. For SSRN, treat `v0.8.0` as the **current public reference release** and `v0.5` as the **published methodology snapshot** the paper describes.

## Submission target

- **Primary network:** FEN — Financial Economics Network
- **Primary topic:** Risk Management & Analysis of Risk eJournal
- **Secondary topics:** Banking & Insurance eJournal; Supervisory & Regulation eJournal; Quantitative Finance eJournal

## Title

> CBSRM: A 7-Layer Open-Source Platform for Cross-Border Systemic Risk Monitoring and Risk Pricing

(Alternative: *Cross-Border Systemic Risk Monitor: A Reproducible Open-Source Implementation of the Canonical Systemic-Risk Triad (SRISK / ΔCoVaR / MES) with Audit-Chain Integrity*)

## Authors

- **Prabhawa Koirala** — Independent researcher / WaverVanir International. Email available on request.

## Abstract (≤ 1,500 characters incl. spaces — SSRN limit)

> CBSRM (Cross-Border Systemic Risk Monitor) is an open-source 7-layer Python platform that reproduces, under one Protocol and one cryptographic audit chain, the three most-cited systemic-risk measures in supervisory literature: SRISK (Brownlees & Engle 2017), ΔCoVaR (Adrian & Brunnermeier 2016), and MES (Acharya, Pedersen, Philippon & Richardson 2017). Alongside the risk-pricing layer, CBSRM ships a stress-indicator layer (CISS-US — full Holló-Kremer-Lo Duca 2012 reimplementation; ECB CISS for EA/US/UK; STLFSI4; OFR-FSI) and a macro-regime layer (yield-curve Estrella-Mishkin recession probit, NFP momentum, FFR change, broad-USD regime, USD/JPY regime, CPI surprise, oil macro, credit-spread regime, 4-state composite). Coverage spans five jurisdictions (US, euro area, UK, Japan, broad USD) with reviewed interpretation labels in five languages. Every computation writes a sha256-linked lifecycle event to an append-only audit chain. The Python Protocol-based architecture lets a new indicator or risk measure ship as one file plus one registration line, with no impact on existing modules. The implementation is pure NumPy at simulate-time (no SciPy / Cython / arch fitting dependency). 555 tests under the current `v0.8.0` reference release; Apache 2.0 license. We illustrate the system with the first live numerical readings (2026-05) across the five jurisdictions and validate the SRISK / ΔCoVaR / MES implementations against published analytical properties.

(Character count check: ~1,490 — within SSRN's 1,500 limit. If revised abstract exceeds, trim the live-readings sentence first.)

## Keywords (SSRN allows up to 12)

1. Systemic risk
2. SRISK
3. CoVaR
4. Marginal Expected Shortfall
5. Financial stability
6. Stress index
7. CISS
8. Open source
9. Audit trail
10. Reproducibility
11. Macroprudential regulation
12. Quantitative risk management

## JEL codes (top 3 mandatory; CBSRM is also tagged with 6 secondary)

**Primary**

- **G01** — Financial Crises
- **G18** — General Financial Markets: Government Policy and Regulation
- **G28** — Financial Institutions and Services: Government Policy and Regulation

**Secondary**

- **C58** — Financial Econometrics
- **G21** — Banks; Depository Institutions
- **G32** — Financial Risk Management
- **E58** — Central Banks and Their Policies
- **F65** — Finance (International)
- **C46** — Specific Distributions; Specific Statistics (covers GARCH-DCC)

## Manuscript file (PDF requirements)

- **Source:** `whitepaper/cbsrm_methodology_v1.md` (~11,000 words, 12 sections)
- **Conversion:**
  ```
  pandoc whitepaper/cbsrm_methodology_v1.md \
    -o cbsrm_methodology_v1.pdf \
    --pdf-engine=xelatex \
    --variable=mainfont:"Times New Roman" \
    --variable=fontsize:11pt \
    --variable=geometry:"margin=1in" \
    --metadata title="CBSRM: A 7-Layer Open-Source Platform for Cross-Border Systemic Risk Monitoring and Risk Pricing" \
    --metadata author="Prabhawa Koirala" \
    --metadata date="2026-05-21" \
    --table-of-contents \
    --number-sections
  ```
  (Requires `pandoc` + a TeX distribution. On Windows: install MiKTeX. On macOS: `brew install pandoc basictex`.)

  If LaTeX isn't installed, fall back to:
  ```
  pandoc whitepaper/cbsrm_methodology_v1.md \
    -o cbsrm_methodology_v1.pdf \
    --metadata title="CBSRM Methodology v0.5" \
    --metadata author="Prabhawa Koirala"
  ```
  which uses the default html-to-pdf path (less polished but submission-eligible).

## Code availability statement (for the SSRN "data / code" field)

> Source code: https://github.com/pravo123/cbsrm (Apache 2.0). All numerical claims in §§8 and 10–12 reproducible via the documented CLI; example walkthrough at `examples/quickstart.py`. Tests: 555 passing under the current `v0.8.0` reference release. The v0.8 series additionally ships CLI (`cbsrm crisis-dossier`), read-only HTTP API (`GET /reports/crisis-dossiers/…`), and standalone offline Streamlit (`streamlit run dashboard/crisis_dossier_viewer.py`) front-ends over the deterministic crisis-window dossier surface; all three return bit-for-bit identical reports.

## Funding statement

> The author received no funding for this work. CBSRM is an independent open-source project.

## Conflict of interest statement

> The author maintains a private companion repository (VolanX) that applies CBSRM's data, indicators, and audit primitives to a multi-broker derivatives execution platform. The public CBSRM repository contains no proprietary execution or trading logic.

## Cover letter (paste into the SSRN cover-letter field)

> Dear FEN editors,
>
> Please find attached the methodology paper for CBSRM (Cross-Border Systemic Risk Monitor), an open-source 7-layer Python platform that reproduces SRISK, ΔCoVaR, and MES — the three most-cited systemic-risk measures in supervisory literature — under one Protocol and one cryptographic audit chain.
>
> The contribution is methodological and infrastructural rather than empirical-new. Specifically: (1) a single Python Protocol unifies stress indicators (CISS, OFR-FSI, STLFSI4), macro regime classifiers (10 indicators across 5 jurisdictions), and risk-pricing measures (SRISK / ΔCoVaR / MES); (2) every computation persists to a sha256-linked audit chain, giving the system regulator-grade reproducibility out of the box; (3) the implementation is pure numpy at simulate-time, with no SciPy / Cython / arch fitting dependency, lowering the activation cost for researchers and supervisory teams to adopt.
>
> I believe the paper is a fit for Risk Management & Analysis of Risk; it would also be appropriate for the Banking & Insurance and Supervisory & Regulation networks. The full source code is Apache 2.0 and publicly available at https://github.com/pravo123/cbsrm. All numerical claims in the paper are reproducible from the documented CLI.
>
> Thank you for considering this submission.
>
> Sincerely,
> Prabhawa Koirala
> WaverVanir International

## Pre-submission checklist

- [ ] Pandoc-PDF generated and visually proofread
- [ ] Abstract under 1,500 characters
- [ ] Title in title case
- [ ] All keywords valid SSRN keywords (no typos)
- [ ] JEL codes correctly formatted
- [ ] Manuscript references the GitHub repo
- [ ] Code link (https://github.com/pravo123/cbsrm) live and tagged `v0.8.0` (current public release; the methodology paper itself describes v0.5)
- [ ] Conflict of interest statement included (VolanX disclosure)
- [ ] Cover letter mentions FEN sub-network
- [ ] Author email provided in author registration
- [ ] CC: BIS Aldasoro + Schrimpf after submission (cold-email templates in `COLD_EMAILS.md`)
