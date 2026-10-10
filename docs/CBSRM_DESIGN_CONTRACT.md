# CBSRM design and workflow contract

The visual baseline is the approved public design at `88f504e1035585ba10510f8a8ca42bec7cb182d6`. The public homepage, Microfinance service and Systemic Risk Desk use the original WaverVanir logo, shared colour tokens, sans-serif typography, card spacing, forms, tables, focus styles and dark/light controls.

## Canonical destinations

- Public information: https://cbsrm.wavervanir.com/
- Microfinance sign-in: https://mfi.cbsrm.wavervanir.com/app/laghubitta-signin.html
- Microfinance product: https://mfi.cbsrm.wavervanir.com/app/laghubitta-service.html
- Systemic Risk Desk: https://app.cbsrm.wavervanir.com/app/

The public website describes capabilities and links straight into these products. Old demo, local workspace, preview and terminal addresses redirect to the canonical product. Historical calculation fixtures remain outside the served site. Sample institutions and sample/live data modes must use the same components and workflow as their real counterpart; do not build a separate polished demo UI.

## Shared assets

`cbsrm-design-system.css`, `cbsrm-ui.css`, `cbsrm-theme.js`, `cbsrm-route.js` and `wavervanir-logo.svg` are byte-identical shared assets. In the public and MFI repositories they live under `site/brand/`; in Desk under `api/src/wavervanir_api/web/brand/`. When updating a shared asset, update all three copies together. Product-specific layout stays in `cbsrm-public.css`, `cbsrm-home.css`, `cbsrm-mfi.css` or `cbsrm-desk.css`.

Theme selection uses `?theme=light|dark`, survives navigation between the products and preserves the product hash. It writes no browser storage. Existing session, permissions, report bindings and data endpoints retain ownership of the workflow. Presentation must not reveal a hidden control, bypass a refusal or invent a service capability.

## Predesigned MFI workflow

All 16 sections use the same screen anatomy: section title, optional guidance, existing task controls, scoped result or honest empty state. Tables scroll inside their region on mobile. Dashboard figures are computed exclusively from the branches returned for the active role view; an absent or invalid balance produces unavailable exposure, never a partial total or a zero.

| Section | Purpose |
| --- | --- |
| Dashboard | Scoped portfolio figures, branch charts, role views and report access |
| Institution | Membership and institution selection |
| Import | Existing extract validation and import |
| Data inputs | Input availability and reporting-period selection |
| Reconciliation | Snapshot totals, differences and source basis |
| Review queue | Scoped warnings and review items |
| Analytics | Supported descriptive portfolio measures |
| Loan grade | Existing account selector, grade components and withheld reasons |
| Action register | Maker/checker action workflow |
| Report | Preview, version generation and printable management brief |
| Independent review | Separate checker and report blockers |
| Downloads | Scoped export types and their access requirements |
| My day and human work | Service-returned calendar, sessions, notes and actions |
| Administration | Existing permission-controlled institution controls |
| Support access | Time-limited, scoped support grants |
| Product guide | Concise workflow guidance; build diagnostics collapsed |

Three future modules have visual placeholders inside the product: CBS/MIS connections on Import, scheduled refresh on Data inputs, and branch geography on Dashboard. Each says **In development**, contains no fabricated data and has no working-looking action. Backend implementation must replace the placeholder in place after the existing service returns authoritative capability, permission and result data. Geography requires verified locations; refresh requires an actual schedule/status; a connection requires a configured and permission-scoped source. Loading, empty, unavailable, failure and success states must use the same components. Do not claim these modules are ready on the public website before the product actually supports them.

## Verification and known limits

Desktop MFI: all 16 sections in both themes. Mobile MFI: all 16 sections at 390 pixels. Desk: sign-in, seven permitted sections and both themes; contained table scrolling and native keyboard-operable navigation. Public and legacy HTML routes audited across all three repositories.

Automated contracts cover static route security, role scoping, UI/service bindings, input flow, human work and truthful chart summaries. The Windows host cannot run the symbolic-link filesystem case; the Linux PR workflow includes it. Existing baseline calculation-artifact mismatches were reproduced against the unchanged baseline and were not repaired as part of the design release. Nepali and Hindi additions are drafts pending native review, recorded in the MFI translation inventory. Public legacy language routes now resolve to the canonical information pages; those information pages are English.

This release changes presentation and navigation. Ongoing backend integration work should consume this contract without restoring old public product replicas.
