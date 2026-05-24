"""
Tests for cbsrm.macro.macro_events — the discrete-event surprise scorer.
"""
from __future__ import annotations

import math

import pytest

from cbsrm.macro import macro_events
from cbsrm.macro.macro_events import (
    get_event_spec,
    list_supported_events,
    score_event,
)


# ─── Schema / basic invariants ──────────────────────────────────────


def test_supported_events_nonempty_and_canonical():
    events = list_supported_events()
    assert len(events) >= 8
    assert events == sorted(events)
    for e in events:
        assert e == e.upper()


def test_score_event_schema_has_required_keys():
    out = score_event("CPI", actual=3.4, consensus=3.2, previous=3.1)
    required = {
        "event", "actual", "consensus", "previous", "unit",
        "surprise", "surprise_z", "abs_z",
        "direction", "severity", "risk_bias",
        "scale_used", "scale_source", "n_history", "spec",
    }
    assert required.issubset(out.keys())


def test_score_event_canonicalises_event_name():
    out = score_event("cpi", actual=3.0, consensus=3.0)
    assert out["event"] == "CPI"


def test_unknown_event_raises():
    with pytest.raises(ValueError, match="unknown event"):
        score_event("MADE_UP_INDICATOR", actual=1.0, consensus=1.0)


def test_non_finite_inputs_raise():
    with pytest.raises(ValueError):
        score_event("CPI", actual=float("nan"), consensus=3.0)
    with pytest.raises(ValueError):
        score_event("CPI", actual=3.0, consensus=float("inf"))


def test_get_event_spec_returns_copy():
    spec = get_event_spec("CPI")
    spec["default_scale"] = 999.0
    # mutating the returned copy must not affect subsequent calls
    fresh = get_event_spec("CPI")
    assert fresh["default_scale"] != 999.0


# ─── Direction × polarity ────────────────────────────────────────────


def test_cpi_hotter_when_actual_above_consensus():
    out = score_event("CPI", actual=3.4, consensus=3.2)
    assert out["direction"] == "hotter_than_expected"
    assert out["risk_bias"] == "rates_up_equities_down"
    assert out["surprise"] == pytest.approx(0.2)
    assert out["surprise_z"] > 0


def test_cpi_cooler_when_actual_below_consensus():
    out = score_event("CPI", actual=2.9, consensus=3.2)
    assert out["direction"] == "cooler_than_expected"
    assert out["risk_bias"] == "rates_down_equities_up"
    assert out["surprise_z"] < 0


def test_in_line_print_is_neutral():
    # Tiny surprise well inside the in-line band → in_line / neutral
    out = score_event("CPI", actual=3.20, consensus=3.21)
    assert out["direction"] == "in_line"
    assert out["risk_bias"] == "neutral"
    assert out["severity"] == "trivial"


def test_unrate_polarity_inverts_hot_cool():
    # Higher UNRATE = labour cooling = dovish = "cooler_than_expected"
    out_high = score_event("UNRATE", actual=4.2, consensus=3.9)
    assert out_high["direction"] == "cooler_than_expected"
    assert out_high["risk_bias"] == "rates_down_equities_up"

    out_low = score_event("UNRATE", actual=3.6, consensus=3.9)
    assert out_low["direction"] == "hotter_than_expected"
    assert out_low["risk_bias"] == "rates_up_equities_down"


def test_initial_claims_polarity_inverts():
    out = score_event("INITIAL_CLAIMS", actual=260.0, consensus=220.0)
    # claims well above consensus → cooler labour
    assert out["direction"] == "cooler_than_expected"


def test_nfp_hotter_is_rates_up_equities_down():
    out = score_event("NFP", actual=300.0, consensus=180.0)
    assert out["direction"] == "hotter_than_expected"
    assert out["risk_bias"] == "rates_up_equities_down"


def test_gdp_growth_event_has_growth_bias():
    out = score_event("GDP", actual=3.5, consensus=2.0)
    assert out["direction"] == "hotter_than_expected"
    # GDP-positive surprise is risk-on for equities, not down
    assert out["risk_bias"] == "rates_up_equities_up"


# ─── Severity ladder ────────────────────────────────────────────────


def test_severity_ladder_monotone_in_abs_z():
    a = score_event("CPI", actual=3.205, consensus=3.20)   # |z| ≈ 0.03
    b = score_event("CPI", actual=3.32, consensus=3.20)   # |z| = 0.8
    c = score_event("CPI", actual=3.45, consensus=3.20)   # |z| ≈ 1.67
    d = score_event("CPI", actual=3.60, consensus=3.20)   # |z| ≈ 2.67
    e = score_event("CPI", actual=4.00, consensus=3.20)   # |z| ≈ 5.33

    rank = {"trivial": 0, "mild": 1, "moderate": 2, "large": 3, "extreme": 4}
    for x, y in zip([a, b, c, d, e], [b, c, d, e, e]):
        assert rank[x["severity"]] <= rank[y["severity"]]
    assert e["severity"] == "extreme"


def test_severity_trivial_when_in_line():
    out = score_event("CPI", actual=3.21, consensus=3.20)
    assert out["severity"] == "trivial"


# ─── Scale source (history vs default) ──────────────────────────────


def test_default_scale_used_when_no_history():
    out = score_event("CPI", actual=3.4, consensus=3.2)
    spec = get_event_spec("CPI")
    assert out["scale_source"] == "default"
    assert out["n_history"] == 0
    assert out["scale_used"] == pytest.approx(spec["default_scale"])
    assert out["surprise_z"] == pytest.approx(0.2 / spec["default_scale"])


def test_history_overrides_default_scale():
    # Caller supplies a tight history → smaller scale → larger z than default
    hist = [0.05, -0.04, 0.02, -0.03, 0.04, -0.05]
    out_with = score_event("CPI", actual=3.4, consensus=3.2, history=hist)
    out_without = score_event("CPI", actual=3.4, consensus=3.2)
    assert out_with["scale_source"] == "history"
    assert out_with["n_history"] == len(hist)
    assert out_with["scale_used"] < out_without["scale_used"]
    assert abs(out_with["surprise_z"]) > abs(out_without["surprise_z"])


def test_history_too_short_falls_back_to_default():
    out = score_event("CPI", actual=3.4, consensus=3.2, history=[0.1])
    assert out["scale_source"] == "default"


def test_history_with_nans_filters():
    hist = [0.1, float("nan"), -0.1, None, 0.05]   # type: ignore[list-item]
    out = score_event("CPI", actual=3.4, consensus=3.2, history=hist)  # type: ignore[arg-type]
    assert out["scale_source"] == "history"
    # n_history reports finite obs actually used (NaN + None filtered)
    assert out["n_history"] == 3


def test_history_zero_variance_falls_back_to_default():
    out = score_event("CPI", actual=3.4, consensus=3.2,
                      history=[0.05, 0.05, 0.05, 0.05])
    assert out["scale_source"] == "default"


# ─── Operator's worked example ──────────────────────────────────────


def test_operator_spec_example_cpi():
    """Mirror the example in the operator's commit definition-of-done."""
    out = score_event(
        event="CPI",
        actual=3.4,
        consensus=3.2,
        previous=3.1,
        unit="yoy_pct",
    )
    assert out["event"] == "CPI"
    assert out["surprise"] == pytest.approx(0.2)
    assert out["direction"] == "hotter_than_expected"
    assert out["risk_bias"] == "rates_up_equities_down"
    assert out["previous"] == 3.1
    assert out["unit"] == "yoy_pct"
    assert math.isfinite(out["surprise_z"])
    assert out["severity"] in {"mild", "moderate", "large", "extreme"}


# ─── Unit echo-through ─────────────────────────────────────────────


def test_unit_echoes_caller_value():
    out = score_event("NFP", actual=240.0, consensus=180.0, unit="k_jobs")
    assert out["unit"] == "k_jobs"


def test_unit_defaults_to_event_spec_when_omitted():
    out = score_event("NFP", actual=240.0, consensus=180.0)
    assert out["unit"] == get_event_spec("NFP")["default_unit"]
