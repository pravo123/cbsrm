# Doctoral research evidence register — draft for independent review

Prepared: 2026-10-18. Status: **working dossier, not a peer-reviewed publication, admission decision, or independent validation**.

## Research question

Under which conditions does a unified, audit-traceable implementation of established systemic-risk and macro-financial methods improve reproducibility, cross-jurisdictional comparability and governance relative to independently implemented baselines?

This is a **proposed question**, not a validated conclusion. Novelty must be established by current literature review and independently reproducible benchmarks. Re-implementation of published methods does not itself establish a new mathematical discovery.

## Evidence portfolio and boundaries

| Artifact | Public link | Available evidence | Missing for doctoral scrutiny |
| --- | --- | --- | --- |
| CBSRM research software | https://github.com/pravo123/cbsrm | Source, Apache-2.0 license, tests, changelog, examples, methodological paper | Independently executed reproduction, external assessment, evidence of adoption/citations and clear novelty |
| Methodology working paper | [whitepaper/cbsrm_methodology_v1.md](../../whitepaper/cbsrm_methodology_v1.md) | Literature framing, algorithm overview, research claims | Update time-stamped results to exact release/commit; complete external replication; professional critical review |
| Derivatives Risk Framework | https://github.com/pravo123/derivatives-risk-framework | Code and documentation concerning trade-risk gates, paper brokering and audit chain | Comparative methodological contribution and external reproduction |
| VolanX public quantitative research | https://github.com/pravo123/VolanX-Quant-Research | Research code and model variants | Unbiased walk-forward tests, data/version provenance, leak checks and independent assessment |
| AML false-positive reduction | https://github.com/pravo123/AML-False-Positive-Reduction | Code and reported classifier results | Dataset provenance, out-of-sample study, reproducibility, credible operating-cost assumptions |
| Private VolanX and CBSRM SaaS | **Not proposed as public evidence** | Could be presented only through a permissioned, redacted research evaluation | Protect customer data, IP, model details, security and confidential partner information |

## Test claims — provenance, not marketing

The public project's [test evidence ledger](../readiness/TEST_EVIDENCE.md) records **1,238 passing public-package tests** from a specified Windows/Python 3.12 run on **2026-10-06**. This is a historical run, **not** a test run performed when this document was written. The same ledger distinguishes privately reviewed components, developer-reported counts and unresolved failures. These must never be combined into a single "tests passing" total.

Before any new public claim: capture exact commit SHA, Python versions, operating systems, command, environment, pass/fail/skip/xfailed totals, CI URL and raw test report. A target of 20,000 tests does not constitute evidence until 20,000 genuinely distinct, meaningful test cases pass under a documented reproducible configuration.

## Publication and attribution status

- The methodology manuscript and SSRN submission instructions in this repository show a **prepared working-paper package**; they do not establish SSRN posting, journal acceptance or peer review.
- SSRN is a preprint platform and does **not** peer-review submissions. See https://www.elsevier.support/ssrn/answer/research-integrity.
- JOSS does conduct peer review of eligible research software. Check its current rules on public development history, AI disclosure, scholarly significance, maintenance and release readiness: https://joss.theoj.org/about.
- Cite an exact Git commit/release. The existence of `CITATION.cff` does not imply a DOI.
- Verify individual intellectual contributions, collaborators and the precise scope of generative-AI assistance before any publication or doctoral submission. Corporate ownership and research authorship are different things.

## Evidence required before pre-application review

1. **One-page personal contribution statement**: what Prabhawa Koirala conceived, coded, validated or directed personally; list contributors truthfully.
2. **Two-page research synopsis**: the problem, questions, methods, comparison with earlier work, novelty, results and limitations.
3. **Version-pinned replication package**: synthetic/open-licensed input data, baselines, notebook/scripts, numerical tolerances, graphs and reproducible command(s).
4. **Independent review**: a qualified academic or domain expert who tests an artifact and provides signed observations. Do not call an internal code review independent peer review.
5. **External impact**: verifiable downstream citations, use, collaborators, independent issues/PRs or case studies, without extrapolating pilots into adoption.
6. **Academic proof**: official bachelor's transcript; MBA conferral/transcript when formally awarded; current CV.
7. **Disclosures**: funding, conflict of interest, institutional affiliations and generative-AI use, as actually applicable.
8. **University eligibility response**: ask whether public research software, working papers and engineering artifacts count as qualifying public works before paying tuition.

## Submission gates

**Gate A — public preprint:** check permissions, source accuracy, evidence, author contributions and references; an SSRN DOI is not peer review.

**Gate B — peer-reviewed JOSS software paper:** verify substantial research-software contribution, documented six-month public development history if software was initially private, release quality, testing, appropriate AI disclosure and editorial suitability. Acceptance is not presumed.

**Gate C — PhD by public/published work:** obtain an actual university determination that these works may be assessed at doctoral level; do not represent code tests or preprints alone as meeting doctoral standards.

No publication upload, university application submission, external outreach, paid purchase or public disclosure of private material is authorized by this register.
