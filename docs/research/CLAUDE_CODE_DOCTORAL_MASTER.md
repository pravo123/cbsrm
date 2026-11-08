# CLAUDE CODE — CBSRM doctoral research-readiness master brief
Owner: Prabhawa Koirala | Date: 2026-10-18
Repo: https://github.com/pravo123/cbsrm
Baseline PR branch: research/doctoral-readiness-20261018

## Objective

Make CBSRM a defensible, reproducible public research-software artifact for legitimate PhD-by-public-works academic consideration and potential journal peer review. The owner requests a stretch target of **20,000 meaningful passing test cases**. This is a goal, not a promised or fabricated number. Academic originality, empirical validity, reproducibility and safety rank ahead of maximizing counts.

This task does NOT authorize emailing universities, publishing to SSRN/JOSS, releasing private material, paying fees, deploying production systems, changing production auth/MFA/SSO, placing trades, making live API calls with secrets, or claiming admissions decisions. Work in a dedicated branch, open reviewable PRs, and request approval for externally consequential actions.

## Coordinate and preserve other work

1. Before editing, inspect git status, existing worktrees/branches, open PRs, recent commits and all in-repo `CLAUDE.md` / `CLAUDE_CODE*` instructions. Contact or coordinate with active local CBSRM integrator and SaaS-readiness agents before shared-source changes. Do not rewrite or delete their work.
2. Confirm exact HEAD, baseline public-package source and existing test evidence. Public docs previously recorded **1,238 passing** on 2026-10-06 (historical run). SaaS synthetic component cohorts and developer-reported larger test counts are DIFFERENT and MUST NOT be summed or presented as independent verification.
3. Distinguish fully public research code from private institutional SaaS, proprietary execution methods, customer data, unpublished invention records and personal information. Never expose private material.
4. Use synthetic or properly licensed public fixtures by default. Never alter production services, brokerage, or credentials. Protect all secrets. Do not invent third-party reviews, customer adoption, accepted publications, peer-review outcomes, ORCID IDs or DOIs.

## Phase A — evidence baseline and reproducibility

- Inspect README, pyproject, tests, examples, notebooks, whitepaper, `docs/readiness/TEST_EVIDENCE.md`, PUBLICATION_BOUNDARIES, and the prepared SSRN package; inventory every supported Python version, dependency, CLI, API and major research module.
- Execute baseline, if dependencies permit: `python -m pip install -e ".[all]"`, `python -m pytest tests -q`, `python tools/verify_readiness_ledger.py`. Keep actual stdout, JUnit XML, pytest node IDs, coverage reports, OS/Python/lockfile provenance and exact git SHA.
- Record an honest test-count ledger with **distinct cases collected vs executed**, passed, failed, errors, skipped, xfailed, and platform/commit provenance. Do not copy an old pass count into a new run.
- Audit references, dated numbers, file links, data-license claims and math/data provenance in the paper. Preserve negatives and documented limitations.
- Audit `CITATION.cff` and attach a reproducible source-citation recipe. Do not insert a DOI before one has been assigned.

## Phase B — doctoral-quality research evidence

Prepare files under `docs/research/`:
1. `RESEARCH_NOVELTY_MATRIX.md`: compare explicitly against canonical CISS, SRISK/LRMES, delta-CoVaR/MES, DebtRank, Diebold–Yilmaz connectedness, FRED/ECB/OFR implementations and relevant open-source work; distinguish copied published methods vs software architecture vs genuinely novel scientific hypotheses. Include bibliographic references.
2. `DOCTORAL_PORTFOLIO_SYNOPSIS.md`: concise 2-page academic synopsis linking CBSRM, Derivatives Risk Framework, quant-model validation and their original contributions. Explain open code, limits, ownership, disclosures, and prospective examinable output.
3. `ARTIFACT_REGISTER.csv`: artifact, URL, DOI if really assigned, dated version/commit, authorship, license, research claim, reproducible evidence, external use/citation proof, current readiness and gaps.
4. `INDEPENDENT_REVIEW_CHECKLIST.md`: executable environment checklist and 3rd-party review procedure; do NOT call internal review independent.
5. `CRITICAL_COMMENTARY_DRAFT.md`: critical evaluation of question, prior art, original contribution, replication results, limitations, collaboration/AI assistance and societal/industry significance. Do not pad the text or call it an accepted thesis.
6. `PREPRINT_JOURNAL_CHECKLIST.md`: SSRN as **preprint screening, not peer review**, and JOSS as peer-reviewed research software, checking its actual current requirements and public history.

Verify contribution attribution with the owner. The repo's whitepaper corporate byline and prepared SSRN package naming Prabhawa require academically consistent attribution, but never falsely claim sole authorship of co-authored or AI-assisted work.

## Phase C — empirical validation, not brochure metrics

Implement a version-pinned, offline-first research experiment harness using public/synthetic test data and explicit expected outputs:
- Replicate CISS and related measures from documented input series; produce error against trustworthy baselines.
- Validate SRISK/LRMES/CoVaR/MES math, units, sensitivity to volatility/correlation, missing data, degenerate edges and timing assumptions.
- Test DebtRank propagation and spillover behavior on independently hand-solvable network examples, zero/negative exposures and cycles.
- Test Diebold–Yilmaz network connectedness invariants and singular/sparse inputs.
- Evaluate macro-surprise and recession/phase models without look-ahead leakage, with timestamps, vintage-data checks and temporal holdout.
- Test deterministic append-only SHA-256 audit chain against tampering, event reorder, cross-platform canonical serialization and failure recovery.
- Label crisis fixtures as synthetic unless actual historical observations and correct vintage provenance are available.
- Include ablation studies, uncertainty estimates, baseline comparators, negative findings, limitations, and numerical tolerances. Do not claim regulatory-grade performance or financial alpha without verification.

Deliver reproducible figures/tables generated from source, alongside hash/seed/environment provenance. Separate numerical calibration, structural tests, software coverage and externally validated research results.

## Phase D — 20,000-case stretch goal with meaningful test design

- Build a risk-based test matrix from real implementations and unique failure modes, with traceability from requirements and mathematically defensible invariants to test IDs.
- Add cases only where unique inputs test a distinct risk boundary, contract, branch, metamorphic invariant, mathematically exhaustive small-domain state, cross-platform behavior, serialization property, or realistic integration path.
- Prefer hypothesis/property-based testing with deterministic seeds and saved minimized regressions where appropriate; add independent reference computations rather than checking implementation against itself.
- Add differential, metamorphic, API schema, CLI, installation, audit-chain, security and numerical-boundary tests. Verify no network or private-provider dependency by default.
- Distinguish smoke, unit, integration, research validation, property, performance/stress and live-required cohorts. Mark slower cohorts so default CI remains reasonably fast.
- Never pad parametrizations with arbitrary index numbers, duplicate assertions, trivial tautologies or test function renames; never double count CI matrix shards or reruns. Collect test node IDs to detect duplication.
- A case is only **passing** when actually executed with a passing assertion. Match `pytest --collect-only` counts to a separately recorded executed-results file, same commit. Report meaningful tested behavior, branch coverage, mutation survivors, platform coverage and flakiness.
- Target as high as justified up to 20,000. **Stop before 20,000 if further cases are artificial**, document the reason, and deliver a candid pass count. An honest 2,000 well-specified cases is preferable to 20,000 ineffective cases.

## Phase E — submission readiness, gates and final report

- Fix defects found by the research harness in small reviewable commits, preserving public APIs or explicitly documenting necessary changes.
- Update README claims only using verified evidence; all quantitative results must link to methods and exact release/commit.
- Prepare JOSS submission materials after confirming public-development-history and reviewer requirements, but DO NOT submit without owner confirmation.
- Prepare SSRN-ready manuscript packaging and checklist, but DO NOT upload without approval. Treat posting as non-peer-reviewed.
- Return a final report with: new branch and PR URLs; modified paths; research originality evidence; actual test execution counts (not targets); reproducibility commands; raw CI provenance; unresolved failures; remaining academic validation; and a 30-day priority plan for Middlesex and Westminster eligibility review.
- Never merge without owner's review; never compromise security, data rights, scientific integrity or institutional accuracy to hit the target.

## Initial deliverable order

1. Clean baseline + evidence register and citation fixes.
2. Novelty matrix + two-page synopsis, referencing actual methods/code.
3. Offline benchmark harness + reproducibility outputs.
4. Research and test improvements with executed case counts.
5. Manuscript + JOSS/SSRN checklist and readiness gaps.
6. Reviewable PR(s) and signed-off, truthful completion report.
