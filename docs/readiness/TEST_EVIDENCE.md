# Test evidence and readiness

Test counts refer to a build, a unit and a runner. Public package tests, independent synthetic component assertions, browser observations, developer-reported tests and full release cases must remain separate.

The public code base for this update is `3a739399685e50bdc68af64fe9c43a4b0b6ca0a5`. The latest privately delivered build reviewed for these records is `dab01ce8fa24630dd7f2b093d9d4c7a656e893cf`; its source is not included in this public update. No unpublished proprietary implementation or patent disclosure is published here.

## Independent component cohorts

| Cohort | Build | Passed | Failed | Scope |
|---|---|---:|---:|---|
| A85-01 | `a85c457e727d` | 12 | 0 | CONCURRENT-AUDIT-TARGETED-REVIEW |
| A85-02 | `a85c457e727d` | 8 | 0 | EXPORT-CURRENT-KIND-REVIEW |
| A85-03 | `a85c457e727d` | 28 | 0 | HUMANWORK-CALENDAR-BOUNDARY-REQUEST-REVIEW |
| A85-04 | `a85c457e727d` | 24 | 0 | HUMANWORK-CONCURRENT-REQUEST-REVIEW |
| A85-05 | `a85c457e727d` | 28 | 0 | HUMANWORK-DISABLED-AI-REQUEST-REVIEW |
| A85-06 | `a85c457e727d` | 29 | 0 | HUMANWORK-EXPLICIT-SHARING-REQUEST-REVIEW |
| A85-07 | `a85c457e727d` | 20 | 0 | HUMANWORK-INTEGRITY-DRAFT-ACK-UI-REVIEW |
| A85-08 | `a85c457e727d` | 20 | 0 | HUMANWORK-PREVIEW-REVISION-BINDING-REVIEW |
| A85-09 | `a85c457e727d` | 26 | 0 | HUMANWORK-REMINDER-RESCHEDULE-REQUEST-REVIEW |
| A85-10 | `a85c457e727d` | 24 | 0 | HUMANWORK-SESSION-REQUEST-REVIEW |
| A85-11 | `a85c457e727d` | 18 | 0 | INTEGRATION-INFLIGHT-POLICY-REVIEW |
| A85-12 | `a85c457e727d` | 22 | 0 | PRELOGIN-BOUNDARIES-REVIEW |
| A85-13 | `a85c457e727d` | 13 | 1 | REPORT-READ-GENERATION-REVIEW |
| A85-14 | `a85c457e727d` | 30 | 0 | SERVICE-FINANCIAL-ASSISTANT-REQUEST-REVIEW |
| A85-15 | `a85c457e727d` | 36 | 0 | SERVICE-IMPORT-RECONCILIATION-REQUEST-REVIEW |
| A85-16 | `a85c457e727d` | 12 | 0 | SERVICE-PRELOGIN-EXPIRY-REQUEST-REVIEW |
| A85-17 | `a85c457e727d` | 16 | 0 | SERVICE-STREAM-BOUNDARY-REQUEST-REVIEW |
| DAB-REPORT | `dab01ce8fa24` | 14 | 0 | DAB-REPORT |
| AI-OUTPUT | `a85c457e727d` | 4 | 3 | AI-OUTPUT |
| DAB-TRIAL | `dab01ce8fa24` | 49 | 0 | DAB-TRIAL |
| DAB-LEDGER | `dab01ce8fa24` | 33 | 1 | DAB-LEDGER |

The first 17 cohorts are a historical a85 checkpoint: 367 assertions, 366 passed and one failed. The changed report behavior was followed up separately at dab with 14 passed and zero failed. The historical failure is preserved; its bounded fix is closed. The 20 local UI/download observations are already inside the integrity cohort and must not be added again.

AI output checking remains open (7 assertions: 4 passed, 3 failed), as does manual-ledger refusal consistency (34 assertions: 33 passed, 1 failed). The AI component's source was unchanged at dab; no real model or customer data was involved. Trial lifecycle is a separate cohort of 49 passed assertions. Earlier archived cohorts are not summed into a new headline.

## Developer-reported counts

The developer reported 4,395 passed / 1 skipped at a85, 65 focused report tests at dab and 932 affected tests / 1 skipped at dab. These are peer claims, not independently rerun product tests. They overlap and must not be added together.

## Full acceptance cases

| Family | Prepared | Accepted |
|---|---:|---:|
| SaaS | 26 | 0 |
| Permissions | 30 | 0 |
| Human workflow | 24 | 0 |
| Integrations | 36 | 0 |
| Commercial | 32 | 0 |
| Owner demo | 14 | 0 |
| Local guide | 44 | 0 |

Prepared case counts are not passing test counts. No full platform release, security certification, regulatory approval or all-vendor compatibility is established.

## Fresh public-package run — 6 October 2026

**1,238 passed; zero failures, errors or skips** on Windows/Python 3.12 against the named public base plus this reporting update. This includes seven new reporting tests. The run took 72.934 seconds and emitted one Starlette/httpx deprecation warning. Cross-platform CI results are separate. It does not execute the privately delivered institutional SaaS build.

## Reproduce the public checks

```console
python -m pip install -e ".[all]"
python -m pytest tests -q
python tools/verify_readiness_ledger.py
```

The public package suite exercises the public source. Readiness-ledger tests check reporting arithmetic and provenance boundaries; they do not exercise the private SaaS product. The latest fresh public run is recorded in `evidence-2026-10-06.json` with its exact code base and unit.
