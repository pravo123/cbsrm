"""
Historical crisis-window dossiers.

A deterministic composition of the v0.8 surfaces — ``macro_events`` +
``macro_replay`` + ``debt_rank`` + ``phase_classifier`` — into a single
human-readable research dossier for one of three canonical episodes:

* ``2008Q4`` — credit / liquidity crisis (Lehman aftermath)
* ``2020Q1`` — COVID volatility shock
* ``2023Q1`` — regional banking stress (SVB / SBNY / FRC)

This module is the first reporting-ready artifact built on top of the
v0.8 research-flow stack. It is intentionally offline, fixture-backed,
and side-effect-free: no live API calls, no external data downloads,
no broker / Telegram / credential / execution wiring. Suitable for
dashboards, SSRN figures, SaaS-tier reports, and unit tests.

Public surface
~~~~~~~~~~~~~~

::

    from cbsrm.diagnostics import build_crisis_dossier, CRISIS_DOSSIER_WINDOWS

    print(CRISIS_DOSSIER_WINDOWS)
    # ('2008Q4', '2020Q1', '2023Q1')

    dossier = build_crisis_dossier("2008Q4")
    print(dossier["phase_label"])           # e.g. "financial_stress"
    print(dossier["network_stress_summary"]["debt_rank"])

Output schema (per dossier)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    {
      "window_id":              str,
      "title":                  str,
      "period":                 {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
      "shock_summary":          str,
      "macro_event_scores":     list[dict]  (score_event outputs),
      "replay_summary":         list[dict]  (replay_macro_events records),
      "network_stress_summary": {
          "debt_rank":         float,
          "iterations":        int,
          "converged":         bool,
          "n_banks":           int,
          "seed_node":         str,
      },
      "phase_label":            str  (one of phase_classifier.PHASE_LABELS),
      "dominant_drivers":       list[str],
      "risk_posture":           str,
      "research_notes":         str,
      "spec": {
          "fixture_version": str,
          "dossier_version": str,
          "composition":     str,
          "sources":         list[str],
      },
    }

Design notes
~~~~~~~~~~~~

* The classification rules and the underlying numerical fixtures are
  pinned in this module (no caller-supplied data). This makes the
  dossier output bit-for-bit deterministic — important for reproducible
  tests, audited replay, and stable demo screenshots.
* The macro / network / feature fixtures are **calibrated to plausible
  contemporaneous prints** (e.g. NFP -240k for Oct 2008) so the
  research narrative reads correctly, but they are NOT a substitute
  for live historical data. Operators wiring a production pipeline
  should swap fixtures for real source data via the existing
  ``cbsrm.data`` adapters.
* API friction with the v0.8 surfaces is documented under the
  "API consistency notes" section of ``docs/v0.8_research_flow.md``;
  this dossier composes around the friction rather than refactoring it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from cbsrm.diagnostics.macro_replay import replay_macro_events
from cbsrm.macro.macro_events import score_event
from cbsrm.macro.phase_classifier import classify_phase
from cbsrm.networks.debt_rank import debt_rank


DOSSIER_VERSION = "1.0.0"
FIXTURE_VERSION = "1.0.0"

CRISIS_DOSSIER_WINDOWS: tuple[str, ...] = ("2008Q4", "2020Q1", "2023Q1")


# ─── Fixtures ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class _CrisisFixture:
    """Pinned fixture data for one dossier window."""

    window_id: str
    title: str
    period_start: str
    period_end: str
    shock_summary: str
    research_notes: str
    sources: tuple[str, ...]
    # Macro event prints (event, date, actual, consensus, previous, unit).
    macro_events: tuple[dict[str, Any], ...]
    # Price panel as a dict mapping series_name -> {date: price}.
    # Kept compact (~window-length daily series).
    price_panel: dict[str, dict[str, float]]
    # 4-bank toy interbank network (L, E, h0, seed node label).
    network_L: tuple[tuple[float, ...], ...]
    network_E: tuple[float, ...]
    network_h0: tuple[float, ...]
    network_seed_label: str
    # Feature snapshot for the phase classifier.
    phase_features: dict[str, float]


def _ramp_prices(start: str, end: str, base: float, slope_per_day: float,
                 jump_date: str | None = None, jump_pct: float = 0.0
                 ) -> dict[str, float]:
    """Build a deterministic price series — linear ramp + optional one-day jump."""
    idx = pd.date_range(start=start, end=end, freq="D")
    p = base + slope_per_day * np.arange(len(idx))
    if jump_date is not None:
        jd = pd.Timestamp(jump_date)
        mask = idx >= jd
        p = np.where(mask, p * (1.0 + jump_pct), p)
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in zip(idx, p)}


def _build_fixtures() -> dict[str, _CrisisFixture]:
    """Construct the three pinned crisis-window fixtures.

    Values are *deterministic illustrations*, calibrated to the
    contemporaneous historical record so the research narrative is
    plausible. Not a substitute for live historical data.
    """
    fx: dict[str, _CrisisFixture] = {}

    # ── 2008Q4 — credit/liquidity crisis (Lehman aftermath) ─────────
    fx["2008Q4"] = _CrisisFixture(
        window_id="2008Q4",
        title="2008Q4 — Credit / Liquidity Crisis (Lehman aftermath)",
        period_start="2008-09-15",
        period_end="2008-12-31",
        shock_summary=(
            "Lehman bankruptcy (Sep 15) triggered global wholesale-funding "
            "freeze. TED spread > 450 bp, money-market funds broke the "
            "buck, equities fell ~30% Q-on-Q. Federal Reserve launched "
            "TARP, CPFF, AMLF, PDCF in rapid succession."
        ),
        research_notes=(
            "Dossier illustrates the systemic-amplification cascade: cooler "
            "macro prints (collapsing payrolls, falling CPI) coincided with "
            "an acute funding shock that DebtRank picks up via concentrated "
            "interbank exposure. The phase classifier flips to financial_stress "
            "long before the unemployment z-score catches up."
        ),
        sources=(
            "BLS Employment Situation (Oct 2008 release)",
            "BLS CPI release (Oct 2008)",
            "Federal Reserve H.4.1 (Oct-Dec 2008)",
        ),
        macro_events=(
            {"event": "NFP",    "date": "2008-10-03",
             "actual": -159.0, "consensus": -100.0,
             "previous": -73.0, "unit": "thousands_jobs"},
            {"event": "NFP",    "date": "2008-11-07",
             "actual": -240.0, "consensus": -200.0,
             "previous": -240.0, "unit": "thousands_jobs"},
            {"event": "CPI",    "date": "2008-10-16",
             "actual": 4.9, "consensus": 5.2,
             "previous": 5.4, "unit": "yoy_pct"},
            {"event": "UNRATE", "date": "2008-10-03",
             "actual": 6.1, "consensus": 6.1,
             "previous": 6.1, "unit": "pct"},
            {"event": "UNRATE", "date": "2008-11-07",
             "actual": 6.5, "consensus": 6.3,
             "previous": 6.1, "unit": "pct"},
        ),
        price_panel={
            "SPY_PROXY": _ramp_prices("2008-09-01", "2008-12-31",
                                      base=130.0, slope_per_day=-0.4,
                                      jump_date="2008-09-29", jump_pct=-0.08),
            "TLT_PROXY": _ramp_prices("2008-09-01", "2008-12-31",
                                      base=95.0, slope_per_day=0.12),
        },
        # 4-bank toy: bank 0 = epicentre (Lehman-like), high cross-exposures,
        # low equity → high amplification.
        network_L=(
            ( 0.0, 35.0, 25.0, 15.0),
            (30.0,  0.0, 20.0, 10.0),
            (20.0, 18.0,  0.0, 12.0),
            (15.0, 10.0,  8.0,  0.0),
        ),
        network_E=(15.0, 22.0, 18.0, 25.0),
        network_h0=(0.80, 0.0, 0.0, 0.0),
        network_seed_label="EPICENTRE_BANK",
        phase_features={
            "growth_z":         -2.0,
            "inflation_z":      -0.5,
            "unemployment_z":    1.4,
            "credit_spread_z":   2.6,
            "volatility_z":      2.8,
            "liquidity_z":      -1.5,
            "systemic_risk_z":   2.2,
            "rates_z":          -1.0,
        },
    )

    # ── 2020Q1 — COVID volatility shock ────────────────────────────
    fx["2020Q1"] = _CrisisFixture(
        window_id="2020Q1",
        title="2020Q1 — COVID Volatility Shock",
        period_start="2020-02-15",
        period_end="2020-04-30",
        shock_summary=(
            "Pandemic lockdowns triggered the fastest equity drawdown in "
            "history (-34% in 33 days). Treasury basis dislocated, "
            "FX swap lines re-opened, Fed cut to ZLB and announced "
            "unlimited QE on Mar 23. NFP collapsed -701k in Mar release; "
            "Apr release printed -20.5M jobs lost."
        ),
        research_notes=(
            "Distinct from 2008: macro prints initially appeared in-line "
            "(Feb CPI = consensus), with the shock entirely in the volatility "
            "and liquidity channels. Phase classifier should route to "
            "financial_stress via the volatility-z override, NOT via "
            "credit-spread blow-out (which happened with a 2-week lag). "
            "DebtRank stays moderate — banks were better capitalised post-Dodd-Frank."
        ),
        sources=(
            "BLS Employment Situation (Mar/Apr 2020 releases)",
            "BLS CPI release (Mar 2020)",
            "Federal Reserve H.4.1 (Mar-Apr 2020)",
        ),
        macro_events=(
            {"event": "CPI",    "date": "2020-03-11",
             "actual": 2.3, "consensus": 2.3,
             "previous": 2.5, "unit": "yoy_pct"},
            {"event": "NFP",    "date": "2020-04-03",
             "actual": -701.0, "consensus": 10.0,
             "previous": 273.0, "unit": "thousands_jobs"},
            {"event": "UNRATE", "date": "2020-04-03",
             "actual": 4.4, "consensus": 3.8,
             "previous": 3.5, "unit": "pct"},
            {"event": "INITIAL_CLAIMS", "date": "2020-03-26",
             "actual": 3283.0, "consensus": 1500.0,
             "previous": 282.0, "unit": "thousands"},
        ),
        price_panel={
            "SPY_PROXY": _ramp_prices("2020-02-01", "2020-04-30",
                                      base=337.0, slope_per_day=-0.5,
                                      jump_date="2020-03-12", jump_pct=-0.18),
            "TLT_PROXY": _ramp_prices("2020-02-01", "2020-04-30",
                                      base=147.0, slope_per_day=0.10,
                                      jump_date="2020-03-09", jump_pct=0.06),
        },
        # Moderate exposures, healthier equity post-Dodd-Frank.
        network_L=(
            ( 0.0, 18.0, 12.0,  8.0),
            (15.0,  0.0, 10.0,  6.0),
            (10.0, 10.0,  0.0,  7.0),
            ( 8.0,  6.0,  5.0,  0.0),
        ),
        network_E=(30.0, 35.0, 28.0, 32.0),
        network_h0=(0.40, 0.0, 0.0, 0.0),
        network_seed_label="MARKET_MAKER_BANK",
        phase_features={
            "growth_z":         -3.0,
            "inflation_z":      -0.2,
            "unemployment_z":    1.0,
            "credit_spread_z":   1.8,
            "volatility_z":      3.5,
            "liquidity_z":      -2.5,
            "systemic_risk_z":   1.7,
            "rates_z":          -2.0,
        },
    )

    # ── 2023Q1 — Regional banking stress ───────────────────────────
    fx["2023Q1"] = _CrisisFixture(
        window_id="2023Q1",
        title="2023Q1 — Regional Banking Stress (SVB / SBNY / FRC)",
        period_start="2023-03-01",
        period_end="2023-05-01",
        shock_summary=(
            "SVB run on Mar 9-10; FDIC receivership Mar 10. Signature Bank "
            "closed Mar 12. First Republic absorbed by JPM May 1. Stress "
            "was concentrated in mid-cap regionals with duration-mismatched "
            "AFS books and uninsured-deposit concentration. Macro prints "
            "(NFP, CPI) remained near-consensus throughout."
        ),
        research_notes=(
            "Most challenging window for the v0.8 stack — macro prints look "
            "almost benign; the entire shock lives in the network/balance-sheet "
            "layer. Phase classifier label should NOT trigger financial_stress "
            "automatically (credit-spread z only moderately wide), but DebtRank "
            "with the right seed bank reveals concentrated regional fragility. "
            "Demonstrates why macro + network signals must be read together."
        ),
        sources=(
            "BLS Employment Situation (Mar 2023 release)",
            "BLS CPI release (Mar 2023)",
            "FDIC press releases (Mar 10, Mar 12, May 1 2023)",
        ),
        macro_events=(
            {"event": "NFP",    "date": "2023-03-10",
             "actual": 311.0, "consensus": 205.0,
             "previous": 504.0, "unit": "thousands_jobs"},
            {"event": "CPI",    "date": "2023-03-14",
             "actual": 6.0, "consensus": 6.0,
             "previous": 6.4, "unit": "yoy_pct"},
            {"event": "UNRATE", "date": "2023-04-07",
             "actual": 3.5, "consensus": 3.6,
             "previous": 3.6, "unit": "pct"},
            {"event": "NFP",    "date": "2023-04-07",
             "actual": 236.0, "consensus": 228.0,
             "previous": 311.0, "unit": "thousands_jobs"},
        ),
        price_panel={
            "SPY_PROXY": _ramp_prices("2023-03-01", "2023-05-01",
                                      base=398.0, slope_per_day=-0.1,
                                      jump_date="2023-03-10", jump_pct=-0.045),
            "TLT_PROXY": _ramp_prices("2023-03-01", "2023-05-01",
                                      base=102.0, slope_per_day=0.07,
                                      jump_date="2023-03-13", jump_pct=0.03),
            "KRE_PROXY": _ramp_prices("2023-03-01", "2023-05-01",
                                      base=64.0, slope_per_day=-0.05,
                                      jump_date="2023-03-09", jump_pct=-0.18),
        },
        # Concentrated regional fragility: bank 0 (SVB-like) has very thin
        # equity and high asymmetric exposure from regional peers.
        network_L=(
            ( 0.0,  4.0,  3.0,  2.0),
            (22.0,  0.0,  6.0,  4.0),
            (18.0,  5.0,  0.0,  3.0),
            (14.0,  3.0,  2.0,  0.0),
        ),
        network_E=( 5.0, 25.0, 22.0, 24.0),
        network_h0=(0.65, 0.0, 0.0, 0.0),
        network_seed_label="REGIONAL_BANK",
        phase_features={
            "growth_z":          0.2,
            "inflation_z":       1.1,
            "unemployment_z":   -0.2,
            "credit_spread_z":   1.0,
            "volatility_z":      0.8,
            "liquidity_z":      -0.6,
            "systemic_risk_z":   1.1,
            "rates_z":           1.2,
        },
    )

    return fx


_FIXTURES: dict[str, _CrisisFixture] = _build_fixtures()


# ─── Helpers ──────────────────────────────────────────────────────


def _events_dataframe(fixture: _CrisisFixture) -> pd.DataFrame:
    df = pd.DataFrame(list(fixture.macro_events))
    df["date"] = pd.to_datetime(df["date"])
    return df


def _prices_dataframe(fixture: _CrisisFixture) -> pd.DataFrame:
    """Return a wide-form price panel indexed by date.

    ``macro_replay.replay_macro_events`` expects the date as the *index*
    (not as a column), per its docstring.
    """
    frames: list[pd.DataFrame] = []
    for series_name, series_map in fixture.price_panel.items():
        s = pd.Series(series_map, name=series_name)
        s.index = pd.to_datetime(s.index)
        frames.append(s.to_frame())
    panel = pd.concat(frames, axis=1).sort_index()
    panel.index.name = "date"
    return panel


def _network_arrays(fixture: _CrisisFixture
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    L = np.array(fixture.network_L, dtype=float)
    E = np.array(fixture.network_E, dtype=float)
    h0 = np.array(fixture.network_h0, dtype=float)
    return L, E, h0


# ─── Public API ───────────────────────────────────────────────────


def list_dossier_windows() -> list[str]:
    """Return the alphabetical list of supported dossier window IDs."""
    return sorted(_FIXTURES.keys())


def get_fixture_snapshot(window_id: str) -> dict[str, Any]:
    """Return a copy of the pinned fixture snapshot for ``window_id``.

    Useful for tests and for downstream callers that want to inspect the
    raw inputs before they hit the v0.8 surfaces.
    """
    if window_id not in _FIXTURES:
        raise ValueError(
            f"unknown crisis window id {window_id!r}. "
            f"supported = {list_dossier_windows()}"
        )
    fx = _FIXTURES[window_id]
    return {
        "window_id": fx.window_id,
        "title": fx.title,
        "period": {"start": fx.period_start, "end": fx.period_end},
        "shock_summary": fx.shock_summary,
        "research_notes": fx.research_notes,
        "sources": list(fx.sources),
        "macro_events": [dict(e) for e in fx.macro_events],
        "price_panel_series": list(fx.price_panel.keys()),
        "network_seed_label": fx.network_seed_label,
        "network_n_banks": len(fx.network_E),
        "phase_features": dict(fx.phase_features),
    }


def build_crisis_dossier(
    window_id: str,
    *,
    fixtures: dict[str, _CrisisFixture] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a deterministic research dossier for one crisis window.

    Parameters
    ----------
    window_id :
        One of :data:`CRISIS_DOSSIER_WINDOWS` (``"2008Q4"`` / ``"2020Q1"`` /
        ``"2023Q1"``).
    fixtures :
        Optional override of the pinned fixture registry, keyed by
        ``window_id``. Tests use this to inject toy data; production
        callers should leave it ``None`` to get the canonical fixtures.
    config :
        Reserved for future composition knobs (replay window sizes,
        DebtRank max_iter, classifier config). Currently unused; supplied
        values are echoed into ``dossier["spec"]["config"]``.

    Returns
    -------
    dict
        Human-readable research dossier — see module docstring for schema.
    """
    registry = fixtures if fixtures is not None else _FIXTURES
    if window_id not in registry:
        raise ValueError(
            f"unknown crisis window id {window_id!r}. "
            f"supported = {sorted(registry.keys())}"
        )

    fixture = registry[window_id]

    # 1) Score each macro print.
    event_scores: list[dict[str, Any]] = []
    for ev in fixture.macro_events:
        scored = score_event(
            event=ev["event"],
            actual=ev["actual"],
            consensus=ev["consensus"],
            previous=ev.get("previous"),
            unit=ev.get("unit"),
        )
        scored = {k: v for k, v in scored.items() if k != "spec"}
        scored["release_date"] = ev["date"]
        event_scores.append(scored)

    # 2) Replay each event across the fixture price panel.
    events_df = _events_dataframe(fixture)
    prices_df = _prices_dataframe(fixture)
    replay_df = replay_macro_events(events_df, prices_df,
                                    pre_window_days=5, post_window_days=5)
    replay_summary = replay_df.assign(
        date=replay_df["date"].dt.strftime("%Y-%m-%d"),
    ).to_dict(orient="records")

    # 3) Propagate the seed shock through the toy interbank network.
    L, E, h0 = _network_arrays(fixture)
    dr = debt_rank(L, E, h0)
    network_stress_summary = {
        "debt_rank": float(dr["debt_rank"]),
        "iterations": int(dr["iterations"]),
        "converged": bool(dr["converged"]),
        "n_banks": int(L.shape[0]),
        "seed_node": fixture.network_seed_label,
    }

    # 4) Classify the macro/market phase from the feature snapshot.
    phase_verdict = classify_phase(dict(fixture.phase_features))

    # 5) Assemble.
    dossier: dict[str, Any] = {
        "window_id": fixture.window_id,
        "title": fixture.title,
        "period": {"start": fixture.period_start, "end": fixture.period_end},
        "shock_summary": fixture.shock_summary,
        "macro_event_scores": event_scores,
        "replay_summary": replay_summary,
        "network_stress_summary": network_stress_summary,
        "phase_label": phase_verdict["phase"],
        "dominant_drivers": list(phase_verdict["dominant_drivers"]),
        "risk_posture": phase_verdict["risk_posture"],
        "research_notes": fixture.research_notes,
        "spec": {
            "fixture_version": FIXTURE_VERSION,
            "dossier_version": DOSSIER_VERSION,
            "composition": (
                "macro_events.score_event → "
                "macro_replay.replay_macro_events → "
                "networks.debt_rank → "
                "macro.classify_phase"
            ),
            "sources": list(fixture.sources),
            "phase_rule_version": phase_verdict["rule_version"],
            "config": dict(config) if config else {},
        },
    }
    return dossier


__all__ = [
    "build_crisis_dossier",
    "CRISIS_DOSSIER_WINDOWS",
    "DOSSIER_VERSION",
    "FIXTURE_VERSION",
    "list_dossier_windows",
    "get_fixture_snapshot",
]
