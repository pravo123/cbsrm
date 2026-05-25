# CBSRM v0.9.0

> v0.9 turns the v0.8 "one composition, three front-ends" pattern into a
> reusable platform: a deterministic report registry/catalog, a second
> executable report (`macro-composite`) shipped through the same CLI +
> HTTP API + Streamlit trio, and a manifest / audit-chain / persistence
> trio that retrofits content-addressed storage and a tamper-evident
> audit chain onto the crisis-dossier surface. Research analytics,
> Apache 2.0, no external dependencies added.

The tag `v0.9.0` will point at the commit that merges this release-prep
branch into `main`. The `v0.8.0` tag remains **frozen** at commit
`410e3ac9f3e2d3e79484571ef16fc92cd3099d10` — v0.9 is strictly additive
on top of it. Body below is copy-paste ready for
<https://github.com/pravo123/cbsrm/releases/new?tag=v0.9.0>.

---

## Highlights

- **Report registry / catalog.** A new deterministic metadata layer
  (`cbsrm.reporting.registry`) exposes every available report through
  one offline, JSON-serializable catalog — surfaced bit-for-bit through
  `cbsrm reports`, `GET /reports`, and a standalone
  `dashboard/report_catalog_viewer.py` Streamlit landing page.
- **Second executable report.** `macro-composite` joins
  `crisis-dossier` as a deterministic, offline, fixture-backed report
  shipped through the same CLI + HTTP API + Streamlit trio
  (`cbsrm macro-composite WINDOW [--format json|markdown]`,
  `GET /reports/macro-composite[/{window_id}[/markdown]]`,
  `streamlit run dashboard/macro_composite_viewer.py`).
- **Crisis-dossier hardening trio.** HTML renderer, deterministic
  manifest, content-addressed sqlite report store, and a tamper-evident
  sqlite audit chain — all opt-in, all exposed across CLI, HTTP API,
  and Streamlit with bit-for-bit-identical bytes.
- **944 tests passing** (up from 555 at v0.8.0).
- **No new runtime dependencies.** FastAPI optional under `cbsrm[api]`;
  Streamlit lazily imported inside each viewer; `markdown` optional
  under `cbsrm[html]`.
- **Offline, deterministic, fixture-backed.** Every new module has
  explicit no-network-IO regression tests that monkeypatch
  `urllib.request.urlopen` and `requests.Session.request` to raise.

---

## What changed since v0.8.0

### Report registry / catalog

| Surface | Invocation |
|---|---|
| Module | `cbsrm.reporting.registry` (`get_report_catalog`, `list_report_ids`, `get_report_metadata`, `REPORT_REGISTRY_VERSION`) |
| CLI | `cbsrm reports` |
| HTTP API | `GET /reports` |
| Streamlit | `streamlit run dashboard/report_catalog_viewer.py` |

Pure metadata layer — never executes a report, never touches the
network, never writes to disk. All return values are fresh deep copies,
JSON-serializable, deterministic.

### `macro-composite` executable report — three front-ends

| Surface | Invocation |
|---|---|
| Module | `cbsrm.reporting.macro_composite_report` (`build_macro_composite_report`, `render_macro_composite_markdown`, `list_macro_composite_windows`, `MACRO_COMPOSITE_WINDOWS`) |
| CLI | `cbsrm macro-composite WINDOW [--format json\|markdown]` |
| HTTP API | `GET /reports/macro-composite`, `GET /reports/macro-composite/{window_id}`, `GET /reports/macro-composite/{window_id}/markdown` |
| Streamlit | `streamlit run dashboard/macro_composite_viewer.py` |

First-cut composition is phase-classifier-only (`cbsrm.macro.classify_phase`
over pinned per-window z-scores for `2008Q4`, `2020Q1`, `2023Q1`).
`classify_regime` integration is deferred pending per-window
sub-indicator-metadata fixtures. All three front-ends return the same
bytes for the same window — pinned by tests.

Registry `surfaces` for `macro-composite` flips atomically once all
three executable front-ends exist on `main`, preserving the
catalog-honesty contract that the registry never advertises a
half-shipped surface.

### Crisis-dossier HTML / manifest / audit / persistence

| Surface | Invocation |
|---|---|
| HTML renderer | `cbsrm.reporting.html_renderer` + `cbsrm crisis-dossier WINDOW --format html`, `GET /reports/crisis-dossiers/{window_id}/html` |
| Deterministic manifest | `cbsrm.reporting.manifest.build_report_manifest` + `cbsrm crisis-dossier --manifest PATH`, `?manifest=true` |
| Audit chain (sqlite) | `cbsrm.reporting.audit_manifest.stamp_manifest_to_db_path` + `cbsrm crisis-dossier --audit-db PATH`, `build_app(audit_db_path=...)` + `?audit=true`, Streamlit "Audit chain (opt-in)" sidebar |
| Content-addressed store | `cbsrm.reporting.persistence` + `cbsrm crisis-dossier --store-db PATH`, `build_app(report_store_db_path=...)` + `?store=true`, `GET /reports/stored/{output_sha256}`, Streamlit "Report store (opt-in)" sidebar |

The manifest is built **once** per render and reused across `--manifest`,
`--audit-db`, and `--store-db`, so the file, the audit row, and the
stored row all describe the same bytes. `output_sha256` is the natural
join key — no audit-chain coupling required.

---

## Quality + footprint

- **944 tests passing** (was 555 at v0.8.0).
- **No new runtime dependencies.** FastAPI stays under `cbsrm[api]`;
  the new `markdown`-package-backed HTML renderer is gated by the
  optional `cbsrm[html]` extra.
- **Lazy imports everywhere new.** Every new HTTP route body imports
  FastAPI deps inside the body; every new Streamlit viewer imports
  `streamlit` inside `render()`. The helper modules under
  `dashboard/*_viewer.py` are pure and unit-testable without
  Streamlit installed.
- **Offline + deterministic regression tests.** Every new
  module monkeypatches `urllib.request.urlopen` and
  `requests.Session.request` to raise, so accidental network IO
  trips a test rather than silently working.
- **Catalog-honesty contract.** Surfaces fields in the registry are
  only flipped to advertise a new front-end after all three
  executable front-ends ship on `main` — pinned by drift-guard
  tests on every slice.

---

## Install / upgrade

```bash
# from PyPI (when published)
pip install --upgrade cbsrm
# with the API extra
pip install --upgrade "cbsrm[api]"
# with the HTML renderer extra
pip install --upgrade "cbsrm[html]"
# with everything
pip install --upgrade "cbsrm[all]"

# from source
git clone https://github.com/pravo123/cbsrm
cd cbsrm
git checkout v0.9.0
pip install -e ".[all]"
```

Verify:

```bash
python -c "import cbsrm; print(cbsrm.__version__)"   # -> 0.9.0
pytest tests/                                        # -> 944 passed
cbsrm reports | jq '.reports[].id'                   # -> crisis-dossier, macro-composite
cbsrm macro-composite 2008Q4 --format markdown | head
cbsrm crisis-dossier 2008Q4 --format html > lehman.html
```

---

## Versions bumped

- `pyproject.toml` `version`: `0.8.0` → `0.9.0`
- `cbsrm/__init__.py` `__version__`: `0.8.0` → `0.9.0`

The `v0.8.0` tag remains **frozen** at commit
`410e3ac9f3e2d3e79484571ef16fc92cd3099d10`. v0.9 is strictly additive
on top of it; no v0.8 surface, byte, or tag was rewritten.

---

## Positioning

The v0.9 surface remains **research analytics**: deterministic,
offline, fixture-backed. The registry / audit-chain / persistence
trio is the foundation for downstream SaaS-tier report generation;
none of it ships hosted, multi-tenant, or auth-gated in this release.

**Not financial advice. No live broker / Telegram / credential /
execution wiring exists in this repository.** Operators wiring the
outputs into a live system must add their own risk controls.

---

## Deferred to v0.10

- `classify_regime` integration in the `macro-composite` report
  (pending per-window sub-indicator-metadata fixtures).
- Manifest / audit-chain / persistence wiring on the `macro-composite`
  report (currently crisis-dossier only).
- PDF rendering on top of the v0.9 HTML renderer.
- `arch`-backed GJR-GARCH-DCC fitter (end-to-end SRISK / MES from raw
  return histories).
- BIS LBS (locational banking statistics) + EER (effective exchange
  rates) adapters.
- Composer layer — unified `PipelineRecord` shape across the v0.8/v0.9
  stages.
- Hosted, auth-gated multi-tenant API.

See `PRODUCT_ROADMAP_v0.9.md` in the repo for the prioritized slice
list.

---

## Acknowledgements

CBSRM stands on a methodology base built by Acemoglu, Acharya, Adrian,
Battiston, Brunnermeier, Diebold, Engle, Holló, Kremer, Lo Duca,
Pedersen, Pesaran, Philippon, Richardson, Shin, Yilmaz, and the BIS /
OFR / ECB / FRED data teams whose public APIs make the entire stack
possible.

Apache 2.0. See [`CHANGELOG.md`](CHANGELOG.md) for the per-slice log
and [`docs/v0.8_research_flow.md`](docs/v0.8_research_flow.md) for the
end-to-end research walkthrough — the v0.9 surfaces compose on top of
the same v0.8 research-flow scaffolding.
