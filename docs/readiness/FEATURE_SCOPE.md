# Microfinance and SaaS feature scope

Status as of 6 October 2026. This is a requirements register, not a list of completed features.
The public research package and the separately reviewed institution SaaS build are different artifacts.
Every original family and named subrequirement remains in scope. Source presence, sample data and peer test reports do not establish a usable authenticated customer journey.

| Register | Entries | Meaning |
|---|---:|---|
| Original requirements | 64 | Source families preserved below |
| Named detail crosswalk | 83 | Original 64 plus 19 details; overlaps, not 83 extra features |
| SaaS and security | 16 | Additive requirements |
| Human workflow | 10 | Notes, calendar, sessions and recovery |
| Integration | 16 | Approved minimal-data CBS/MIS interfaces |
| Commercial | 16 | Trial, quote and payment lifecycle |
| Owner demo | 14 | Prepared acceptance cases |
| Product page | 40 | Substantive promises mapped to the above scope |
| User value backlog | 32 | Proposed improvements, no completion count |

## Original requirement families

| ID | Required capability | Release disposition |
|---|---|---|
| R01 | Existing CBS compatibility | Full acceptance open |
| R02 | Integration/ETL and data warehouse | Full acceptance open |
| R03 | Borrower score and configurable credit grade | Full acceptance open |
| R04 | Repayment, savings, income/cash-flow and external exposure | Full acceptance open |
| R05 | Loan utilisation, restructuring and loan-cycle risk | Full acceptance open |
| R06 | Separate loan risk score and A-E grade | Full acceptance open |
| R07 | New/repeat borrower segmentation | Full acceptance open |
| R08 | Group/centre risk | Full acceptance open |
| R09 | Multiple borrowing and total external exposure | Full acceptance open |
| R10 | Live credit-information/CIB connection | Full acceptance open |
| R11 | PAR 1, 7, 30, 60, 90 and 180 | Full acceptance open |
| R12 | NPL, overdue, rescheduling, restructuring and write-offs | Full acceptance open |
| R13 | Collection efficiency and recovery rates | Full acceptance open |
| R14 | Migration, roll rates and delinquency trend | Full acceptance open |
| R15 | True vintage/origination cohorts | Full acceptance open |
| R16 | First-payment default | Full acceptance open |
| R17 | Geographic hierarchy and municipal drill-down | Full acceptance open |
| R18 | Product and sector concentration including agriculture/livestock | Full acceptance open |
| R19 | Borrower-segment and high-exposure concentration | Full acceptance open |
| R20 | Branch composite index, ranking, trends and configurable weights | Full acceptance open |
| R21 | Institution financial KPIs: CAR, ROA, ROE, cost of funds, expenses, yield, coverage | Full acceptance open |
| R22 | Staff turnover, branch/officer productivity and cash handling | Full acceptance open |
| R23 | Governance: policy exceptions, approval overrides, audit findings and corrections | Full acceptance open |
| R24 | KYC, AML and documentation exceptions | Full acceptance open |
| R25 | Cyber/IT: access monitoring, role control, backups and recovery | Full acceptance open |
| R26 | Duplicate/contact/address/identity anomaly review | Full acceptance open |
| R27 | Bank-account and photographic identity relationships | Full acceptance open |
| R28 | Officer approval, disbursement, restructuring, collection and override anomalies | Full acceptance open |
| R29 | Transaction anomalies: cash, reversals, settlements, same-day events and adjustments | Full acceptance open |
| R30 | Investigation/review queue | Full acceptance open |
| R31 | Multi-signal early warning and severity levels | Full acceptance open |
| R32 | SMS/email/dashboard routing and scheduled escalation | Full acceptance open |
| R33 | Risk appetite and near/breached/no-data states | Full acceptance open |
| R34 | Regulatory actual/threshold/variance/trend/exception/action | Full acceptance open |
| R35 | Liquidity ratio, cash position and customer ALM inputs | Full acceptance open |
| R36 | Loan/savings/funding maturities, inflows/outflows and mismatch | Full acceptance open |
| R37 | Funding concentration and borrowing-cost stress | Full acceptance open |
| R38 | Credit, collection, agriculture, regional and funding shock families | Full acceptance open |
| R39 | Collection delay scenarios 15/30/60 days | Full acceptance open |
| R40 | Stress impact chain: overdue/NPL/provisions/profit/capital/liquidity | Full acceptance open |
| R41 | Reverse stress and threshold crossing | Full acceptance open |
| R42 | Nepal risk map with hierarchy and exposure/risk drill-down | Full acceptance open |
| R43 | Agricultural exposure and seasonal repayment intelligence | Full acceptance open |
| R44 | Rainfall, flood, drought, landslide, crop, commodity and disease feeds | Full acceptance open |
| R45 | Explain My Risk and transparent component reasons | Full acceptance open |
| R46 | AI default prediction | Full acceptance open |
| R47 | Collection prediction | Full acceptance open |
| R48 | Systemic/macro analytics retained as advanced optional capability | Full acceptance open |
| R49 | Nepal-listed MFI systemic and wholesale-retail network analysis | Full acceptance open |
| R50 | CEO/Board/Risk/Credit/Branch/Loan-officer role views | Full acceptance open |
| R51 | Audit lineage and reproducible computation | Full acceptance open |
| R52 | Board/management report and regulatory reporting | Full acceptance open |
| R53 | Practical pilot: 12-24 months of authorised history | Full acceptance open |
| R54 | Pilot duration and usefulness/accuracy/explainability/feasibility evaluation | Full acceptance open |
| R55 | CBS/MIS comparison and institution presentation | Full acceptance open |
| R56 | Risk hierarchy and integration/scenario visuals | Full acceptance open |
| R57 | Institutional website, art, real cockpit screenshot and localisation | Full acceptance open |
| R58 | Guided imports, repeat-month runs and reduced manual preparation | Full acceptance open |
| R59 | Grounded assistant for risk-team questions and committee summaries | Full acceptance open |
| R60 | English/Nepali language and understandable management labels | Full acceptance open |
| R61 | Financial case, market opportunity, proposed support and partner packet | Full acceptance open |
| R62 | Professional black-suit avatar presentation and minimal live involvement | Full acceptance open |
| R63 | Unsent meeting message with reviewed attachments | Full acceptance open |
| R64 | Chained development checks and final handoff | Full acceptance open |

## Current bounded evidence and remaining work

Independently checked components cover synthetic imports and controls, note sharing and recovery, action preview, calendar placement, report generation and review, current-policy cancellation, signed-export capability, request limits, pre-login expiry and trial records. Full provider, hosted-operation and customer journeys remain open.

Next priorities are a real signed-in workspace, maintained identity verification, durable tenant storage, a useful no-model guide, authoritative AI output checking, native-language and accessibility review, all named analytics in customer paths and independently verified commercial workflows.

Actual configured provider/MFA, bank or Stripe checkout, institution-hosted recovery, live vendor conformance, predictive-model validation and private local inference are not accepted. No automatic loan/report approval, CBS financial write, public mock login or silent cloud AI fallback is authorized.

See [test evidence](TEST_EVIDENCE.md) and [publication boundaries](PUBLICATION_BOUNDARIES.md).
