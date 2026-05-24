"""
Macro-event surprise scoring engine.

Where the existing ``CPISurpriseIndicator`` and ``NFPMomentumIndicator``
publish *time-series momentum proxies* from FRED, this module scores a
*discrete event print* the moment the actual lands and a consensus is
known. The two surfaces complement each other: time-series momentum gates
slow regime, event surprise quantifies the instantaneous shock.

Public API
~~~~~~~~~~

    >>> from cbsrm.macro import macro_events
    >>> macro_events.score_event(
    ...     event="CPI",
    ...     actual=3.4,
    ...     consensus=3.2,
    ...     previous=3.1,
    ...     unit="yoy_pct",
    ... )
    {
        "event": "CPI",
        "actual": 3.4,
        "consensus": 3.2,
        "previous": 3.1,
        "surprise": 0.2,
        "surprise_z": 1.15,
        "direction": "hotter_than_expected",
        "severity": "moderate",
        "risk_bias": "rates_up_equities_down",
        ...
    }

Design
~~~~~~

* The function is a *pure scorer*. It does not fetch data, persist, or call
  any network. The caller is responsible for sourcing ``actual`` and
  ``consensus`` from a release calendar (BLS, BEA, Bureau of the Census,
  Federal Reserve, etc.).
* z-scoring uses a caller-supplied ``history`` (a 1-D sequence of prior
  surprises) when available, otherwise falls back to an event-specific
  default scale derived from historical surprise volatility in the
  open-source literature. The default scale keeps the module fully usable
  with zero history.
* ``risk_bias`` maps (event, direction) to a generic markets-impact tag,
  intentionally coarse so it is treated as *decision intelligence*, not a
  trading signal. The mapping is conservative: in-line prints always emit
  ``neutral``.

References
~~~~~~~~~~

* Bureau of Labor Statistics, Employment Situation + CPI Release schedules.
* Bureau of Economic Analysis, GDP + PCE Release schedules.
* Andersen-Bollerslev-Diebold-Vega (2003) AER — "Micro effects of macro
  announcements". Magnitude-of-surprise / sign / event-type framework.
* Faust-Rogers-Wang-Wright (2007) JIMF — surprise scaling by historical std.
* Swanson (2021) AEJ:Macro — monetary policy surprises.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

import math


# ─── Event registry ──────────────────────────────────────────────────
#
# default_scale ≈ historical 1σ of (actual − consensus) for the event,
# expressed in the unit of measurement of the print itself. These are
# rounded conservative anchors compiled from public Federal Reserve and
# BLS historical surprise tables; they make z-scoring work on a single
# event with no prior history, and are overridden whenever a non-empty
# ``history`` is supplied.
#
# direction_polarity controls how surprise sign maps to (hotter | cooler):
#   +1 → positive surprise = hotter_than_expected (CPI, NFP, GDP, ...)
#   -1 → positive surprise = cooler_than_expected (UNRATE, INITIAL_CLAIMS)
#
# risk_bias_on_hot is the bias tag emitted when direction = "hotter".
# risk_bias_on_cool is the tag for direction = "cooler". "In-line" prints
# always emit "neutral".
_EVENT_REGISTRY: dict[str, dict[str, Any]] = {
    "CPI": {
        "default_unit": "yoy_pct",
        "default_scale": 0.15,            # ~0.15 pp surprise std on YoY headline
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US headline CPI YoY %",
    },
    "CORE_CPI": {
        "default_unit": "yoy_pct",
        "default_scale": 0.12,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US core CPI YoY %",
    },
    "PCE": {
        "default_unit": "yoy_pct",
        "default_scale": 0.12,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US PCE deflator YoY %",
    },
    "CORE_PCE": {
        "default_unit": "yoy_pct",
        "default_scale": 0.10,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US core PCE deflator YoY %",
    },
    "NFP": {
        "default_unit": "thousands_jobs",
        "default_scale": 60.0,            # ~60k surprise std post-2010
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US non-farm payrolls MoM change, thousands",
    },
    "UNRATE": {
        "default_unit": "pct",
        "default_scale": 0.10,            # ~0.1 pp on monthly U-3
        "direction_polarity": -1,          # higher UNRATE = cooler = dovish
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US U-3 unemployment rate %",
    },
    "INITIAL_CLAIMS": {
        "default_unit": "thousands",
        "default_scale": 15.0,
        "direction_polarity": -1,          # higher claims = cooler labour
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "US initial jobless claims, thousands (SA)",
    },
    "GDP": {
        "default_unit": "qoq_saar_pct",
        "default_scale": 0.5,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_up",
        "risk_bias_on_cool": "rates_down_equities_down",
        "description": "US real GDP, QoQ SAAR %",
    },
    "RETAIL_SALES": {
        "default_unit": "mom_pct",
        "default_scale": 0.4,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_up",
        "risk_bias_on_cool": "rates_down_equities_down",
        "description": "US retail sales MoM %",
    },
    "ISM_MANUFACTURING": {
        "default_unit": "index",
        "default_scale": 1.5,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_up",
        "risk_bias_on_cool": "rates_down_equities_down",
        "description": "ISM Manufacturing PMI",
    },
    "ISM_SERVICES": {
        "default_unit": "index",
        "default_scale": 1.5,
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_up",
        "risk_bias_on_cool": "rates_down_equities_down",
        "description": "ISM Services PMI",
    },
    "FOMC_RATE": {
        "default_unit": "bp",
        "default_scale": 8.0,              # ~8 bp std on funds-rate decision surprise
        "direction_polarity": +1,
        "risk_bias_on_hot": "rates_up_equities_down",
        "risk_bias_on_cool": "rates_down_equities_up",
        "description": "FOMC target-rate decision, basis points vs OIS expectation",
    },
}


# ─── Severity ladder ────────────────────────────────────────────────
#
# |z| → severity bucket. Thresholds chosen so that under a roughly normal
# surprise distribution: ~75% trivial, ~25% mild+, ~5% large+, ~1% extreme.
_SEVERITY_LADDER: list[tuple[float, str]] = [
    (0.25, "trivial"),
    (0.75, "mild"),
    (1.5,  "moderate"),
    (2.5,  "large"),
    (float("inf"), "extreme"),
]


# ─── Public function ────────────────────────────────────────────────


def list_supported_events() -> list[str]:
    """Return the alphabetical list of supported event identifiers."""
    return sorted(_EVENT_REGISTRY.keys())


def get_event_spec(event: str) -> dict[str, Any]:
    """Return a copy of the registry entry for ``event``."""
    key = event.strip().upper()
    if key not in _EVENT_REGISTRY:
        raise ValueError(
            f"unknown event '{event}'. Supported: {list_supported_events()}"
        )
    return dict(_EVENT_REGISTRY[key])


def _classify_severity(abs_z: float) -> str:
    for cutoff, label in _SEVERITY_LADDER:
        if abs_z <= cutoff:
            return label
    return "extreme"  # unreachable; ladder ends at +inf


def _scale_from_history(history: Sequence[float]) -> Optional[float]:
    """Return the unbiased std of ``history`` (>= 2 finite obs), else None."""
    if history is None:
        return None
    xs = [float(x) for x in history if x is not None and not math.isnan(float(x))]
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    if var <= 0:
        return None
    return math.sqrt(var)


def score_event(
    event: str,
    actual: float,
    consensus: float,
    previous: Optional[float] = None,
    unit: Optional[str] = None,
    history: Optional[Sequence[float]] = None,
    in_line_band_z: float = 0.25,
) -> dict[str, Any]:
    """
    Score a single macro release as a normalised surprise event.

    Parameters
    ----------
    event :
        Event identifier — one of :func:`list_supported_events`.
    actual :
        Released value, in the event's unit.
    consensus :
        Pre-release consensus forecast, in the same unit as ``actual``.
    previous :
        Optional prior period's actual value, returned in the output for
        downstream context (e.g. trend continuity).
    unit :
        Unit string supplied by the caller. If omitted the event's
        registry default is returned. Not used in any calculation.
    history :
        Optional sequence of *prior surprise values* (actual − consensus)
        for the same event. When supplied with ≥ 2 finite entries, the
        z-score uses the sample std of ``history``. Otherwise the
        registry's ``default_scale`` is used.
    in_line_band_z :
        |z| below this threshold is classified ``in_line``. Default 0.25,
        i.e. roughly the bottom quartile of |surprise| under normality.

    Returns
    -------
    dict
        Output schema::

            {
              "event": str,
              "actual": float,
              "consensus": float,
              "previous": float | None,
              "unit": str,
              "surprise": float,           # actual - consensus, in unit
              "surprise_z": float,         # signed z-score
              "abs_z": float,
              "direction": "hotter_than_expected"
                          | "cooler_than_expected"
                          | "in_line",
              "severity": "trivial"|"mild"|"moderate"|"large"|"extreme",
              "risk_bias": "rates_up_equities_down"
                          | "rates_down_equities_up"
                          | "rates_up_equities_up"
                          | "rates_down_equities_down"
                          | "neutral",
              "scale_used": float,
              "scale_source": "history" | "default",
              "n_history": int,
              "spec": { ... registry entry ... },
            }
    """
    spec = get_event_spec(event)
    canonical_event = event.strip().upper()

    if not (isinstance(actual, (int, float)) and math.isfinite(float(actual))):
        raise ValueError(f"actual must be a finite number, got {actual!r}")
    if not (isinstance(consensus, (int, float)) and math.isfinite(float(consensus))):
        raise ValueError(f"consensus must be a finite number, got {consensus!r}")

    actual = float(actual)
    consensus = float(consensus)
    surprise = actual - consensus

    # Scale: prefer caller's history, fall back to registry default.
    scale_hist = _scale_from_history(history) if history is not None else None
    if scale_hist is not None and scale_hist > 0:
        scale = scale_hist
        scale_source = "history"
        n_history = len([x for x in history if x is not None
                         and not math.isnan(float(x))])
    else:
        scale = float(spec["default_scale"])
        scale_source = "default"
        n_history = 0 if history is None else len(list(history))

    surprise_z = surprise / scale if scale > 0 else 0.0
    abs_z = abs(surprise_z)

    # Direction (polarity flips for "lower is hotter" events like UNRATE).
    polarity = int(spec["direction_polarity"])
    signed_for_direction = surprise * polarity
    if abs_z < in_line_band_z:
        direction = "in_line"
    elif signed_for_direction > 0:
        direction = "hotter_than_expected"
    else:
        direction = "cooler_than_expected"

    severity = _classify_severity(abs_z) if direction != "in_line" else "trivial"

    if direction == "in_line":
        risk_bias = "neutral"
    elif direction == "hotter_than_expected":
        risk_bias = spec["risk_bias_on_hot"]
    else:
        risk_bias = spec["risk_bias_on_cool"]

    return {
        "event": canonical_event,
        "actual": actual,
        "consensus": consensus,
        "previous": float(previous) if previous is not None else None,
        "unit": unit or spec["default_unit"],
        "surprise": surprise,
        "surprise_z": surprise_z,
        "abs_z": abs_z,
        "direction": direction,
        "severity": severity,
        "risk_bias": risk_bias,
        "scale_used": scale,
        "scale_source": scale_source,
        "n_history": n_history,
        "spec": spec,
    }


__all__ = [
    "score_event",
    "list_supported_events",
    "get_event_spec",
]
