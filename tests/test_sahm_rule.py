"""Tests for cbsrm.macro.sahm_rule.SahmRuleIndicator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.indicators.base import IIndicator
from cbsrm.macro.sahm_rule import (
    MIN_OBS_REQUIRED,
    THRESHOLD_EARLY_WARNING_PP,
    THRESHOLD_RECESSION_PP,
    SahmRuleIndicator,
)


def _unrate_series(values: list[float], start: str = "2010-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"UNRATE": values}, index=idx)


# ─── Protocol conformance ──────────────────────────────────────────


def test_implements_protocol():
    assert isinstance(SahmRuleIndicator(), IIndicator)


def test_required_series_unrate():
    assert SahmRuleIndicator().required_series() == ["UNRATE"]


def test_id_and_version():
    s = SahmRuleIndicator()
    assert s.id == "SAHM-RULE-US"
    assert s.version == "1.0.0"


# ─── Rejection cases ───────────────────────────────────────────────


def test_compute_raises_on_missing_column():
    with pytest.raises(ValueError, match="UNRATE"):
        SahmRuleIndicator().compute(pd.DataFrame({"WRONG": [1.0]}))


def test_compute_empty_returns_empty_with_zero_obs():
    res = SahmRuleIndicator().compute(_unrate_series([]))
    assert res.values.empty
    assert res.metadata["n_obs"] == 0


def test_compute_insufficient_history():
    # Fewer than 15 months → no Sahm value computable
    res = SahmRuleIndicator().compute(_unrate_series([4.0] * 10))
    assert res.values.empty
    assert res.metadata.get("classification") == "INSUFFICIENT_HISTORY"


# ─── Classification ────────────────────────────────────────────────


def test_normal_classification_flat_unrate():
    # UNRATE stays flat at 4.0 for 24 months → Sahm = 0 → NORMAL
    res = SahmRuleIndicator().compute(_unrate_series([4.0] * 24))
    assert res.metadata["classification"] == "NORMAL"
    assert res.metadata["latest_sahm_pp"] == pytest.approx(0.0, abs=1e-9)


def test_recession_triggered_classification():
    # Flat at 3.5 for 12 months, then ramp to 4.5 over 6 months → Sahm > 0.5
    base = [3.5] * 12
    ramp = [3.5 + (i + 1) * (1.0 / 6) for i in range(6)]
    res = SahmRuleIndicator().compute(_unrate_series(base + ramp))
    assert res.metadata["latest_sahm_pp"] >= THRESHOLD_RECESSION_PP
    assert res.metadata["classification"] == "RECESSION_TRIGGERED"


def test_early_warning_classification():
    # Flat at 4.0 for 12 months, then ramp to 4.4 over 5 months
    # 3m avg by end = (4.2 + 4.3 + 4.4) / 3 = 4.3
    # 12m min of 3m avg = 4.0 → Sahm = 0.40 → EARLY_WARNING band
    base = [4.0] * 12
    ramp = [4.0 + (i + 1) * 0.1 for i in range(5)]
    res = SahmRuleIndicator().compute(_unrate_series(base + ramp))
    sahm = res.metadata["latest_sahm_pp"]
    assert THRESHOLD_EARLY_WARNING_PP <= sahm < THRESHOLD_RECESSION_PP
    assert res.metadata["classification"] == "EARLY_WARNING"


def test_falling_unrate_yields_normal():
    # Improving labour market → Sahm = 0 (12m min refreshes downward)
    res = SahmRuleIndicator().compute(_unrate_series(
        [6.0, 5.8, 5.6, 5.4, 5.2, 5.0, 4.9, 4.8, 4.7, 4.6, 4.5,
         4.4, 4.3, 4.2, 4.1, 4.0, 3.9, 3.8, 3.7, 3.6],
    ))
    assert res.metadata["classification"] == "NORMAL"


def test_metadata_includes_i18n():
    res = SahmRuleIndicator().compute(_unrate_series([4.0] * 20))
    assert "interpretation_i18n" in res.metadata
    assert "en" in res.metadata["interpretation_i18n"]
    assert "ja" in res.metadata["interpretation_i18n"]


def test_metadata_includes_thresholds():
    res = SahmRuleIndicator().compute(_unrate_series([4.0] * 20))
    t = res.metadata["thresholds_pp"]
    assert t["recession"] == THRESHOLD_RECESSION_PP
    assert t["early_warning"] == THRESHOLD_EARLY_WARNING_PP


def test_min_obs_constant_value():
    assert MIN_OBS_REQUIRED == 15


def test_2024_style_borderline_trigger_synthetic():
    # Mimic 2023-24 pattern: low UNRATE then slow rise crossing 0.50
    base = [3.5, 3.6, 3.5, 3.5, 3.4, 3.5, 3.6, 3.7, 3.7, 3.8, 3.8, 3.9]
    rise = [3.9, 4.0, 4.1, 4.0, 4.1, 4.2]
    res = SahmRuleIndicator().compute(_unrate_series(base + rise))
    # Should at least be in EARLY_WARNING territory by the end
    assert res.metadata["classification"] in ("EARLY_WARNING", "RECESSION_TRIGGERED")
