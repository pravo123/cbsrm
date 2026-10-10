# CBSRM design system

Canonical tokens: `site/brand/cbsrm-design-system.css`. The blue `#45b8ef`,
gold `#e3b75e`, green `#4bc18c` and black `#0b0f14` preserve the existing
owner-approved WaverVanir identity in `wavervanir-palette.css` and
`wavervanir-unified.css`. Light neutrals retain the existing launch palette.
Do not replace these identity colours with a new teal palette.

## Theme and type

Dark is the default. A visible Dark/Light control sets the root `data-theme`;
store only the preference and handle unavailable storage. The static preview
uses `cbsrm.preview.theme`; the authenticated application must use its own
existing preference contract after inspection. Never store financial or session
records as part of a theme preference. Render the saved theme before paint.

Use `--wv-bg`, `--wv-card`, `--wv-surface`, `--wv-text`, `--wv-muted` and
`--wv-border` for semantic surfaces, text and rules. The token file declares
variables only; importing it does not alter permissions or application state.
Use the existing system sans stack, 16px body type, readable 1.55–1.75 line
height and short labels. Headings use weight 650 and restrained negative
tracking. Do not use colour alone for severity or approval state.

## Logo, layout and imagery

Use the original `site/brand/wavervanir-logo.svg` unchanged. Its intrinsic
viewBox is 640 × 410: preserve that ratio with `height:auto`, not a square
icon box. Full desktop lockup width is 154px, mobile 96px; use the dark
`#0e141b` navigation backplate for legibility in both themes. Keep CBSRM text
and descriptive alternative text. Never redraw, crop or recolour the logo.

Spacing uses 4, 8, 12, 16, 24 and 32px tokens. Controls, cards and panels use
8, 12 and 18px corners. Preserve the approved preview's portfolio/map/trend
layout. Its hero image is 430px on desktop, 380px on tablet, 310px on mobile
and 260px on small screens. Reuse existing approved connectivity and Nepal
landscape assets; keep image descriptions and source labels.

## Charts, maps and interaction

Use `--wv-chart` for data series, blue for network links and gold for the
selected links/nodes. Gold, green and elevated rose can distinguish series
with visible text/legends. Grid lines use the semantic border. Tooltip or
explanation values retain dates, units, missing state and source identity.
Actual country outline and synthetic marker/risk data must be labelled
separately. A rendered graph does not prove a DebtRank calculation.

Keyboard focus uses `--wv-focus`; selected filters expose `aria-pressed`.
Keep native buttons, labelled groups, live updated summary values, a skip link,
responsive layouts and `prefers-reduced-motion`. Exercise contrast and
keyboard operation in the actual browser before acceptance.

## Public and authenticated reuse

`site/preview/saas-visual-refresh.css` imports these tokens and maps its
presentation aliases to them. The public replacement can reuse the same
CSS/JS under `/preview/` when its HTML moves to `site/index.html`; root the
two references explicitly. Existing Netlify publishes `site/` without a
build step. Preserve policy/authentication/navigation links, synthetic labels
and a reversible source checkpoint. No private pricing or institution data
belongs on the public homepage.

The authenticated target is **https://app.cbsrm.wavervanir.com**. Its actual
deployment/repository mapping and logged-in layout must be verified first;
do not assume it is the microfinance service or replace it with this static
preview. Map existing app semantic colours to these tokens, retain all
workflow hooks/roles/audit/security contracts and reuse the original logo.
The token module is ready; authenticated app integration and acceptance are
**not implemented or verified by this design packet**. A calendar, report,
approval or import button may appear only when backed by its real workflow.

This guide records presentation decisions, not production readiness,
institutional validation, model calibration or measured labour savings.
