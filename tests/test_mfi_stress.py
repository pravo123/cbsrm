"""Hand-calculated simultaneous stress, capital and liquidity arithmetic."""
from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from cbsrm.mfi import BUCKETS, DEFAULT_CONFIG, apply_scenario


@pytest.fixture
def segments():
    return pd.DataFrame([
        ["Agriculture", "Bagmati", 100, 200, 300, 400, 500],
    ], columns=["sector", "province", *BUCKETS])


@pytest.fixture
def balance_sheet():
    return {
        "capital_npr": 500, "rwa_npr": 2000, "liquid_assets_npr": 300,
        "inflows_90d_npr": 200, "outflows_90d_npr": 400, "borrowings_npr": 1000,
    }


def test_base_scenario_hand_calculated(segments, balance_sheet):
    result = apply_scenario(segments, balance_sheet, {"id": "base"})
    assert result.pop("scenario_id") == "base"
    assert result.pop("buckets") == dict(zip(BUCKETS, [100, 200, 300, 400, 500], strict=True))
    assert result == pytest.approx({
        "gross_npr": 1500, "par30": 0.8, "par90": 0.6,
        "provisions_npr": 786, "delta_provisions_npr": 0, "nii_hit_npr": 0,
        "capital_npr": 500, "car": 0.25, "liquidity_gap_90d_npr": 100,
    })


def test_combined_scenario_hand_calculated(segments, balance_sheet):
    result = apply_scenario(segments, balance_sheet, {
        "id": "combined", "label": "Synthetic stress", "base_shift": 0.2,
        "funding_cost_bps": 200, "inflow_haircut": 0.25, "outflow_mult": 1.2,
    })
    # Pre-shock movements: 20,40,60,80 NPR. Last bucket retains all 500.
    assert result.pop("scenario_id") == "combined"
    assert result.pop("buckets") == pytest.approx(dict(zip(BUCKETS, [80, 180, 280, 380, 580], strict=True)))
    # Provisions .8 + 9 + 70 + 190 + 580 = 849.8, up 63.8.
    # Funding hit 1000*200/10000=20, no 90-day prorating.
    assert result == pytest.approx({
        "gross_npr": 1500, "par30": 1240 / 1500, "par90": 960 / 1500,
        "provisions_npr": 849.8, "delta_provisions_npr": 63.8, "nii_hit_npr": 20,
        "capital_npr": 416.2, "car": 0.2081, "liquidity_gap_90d_npr": -30,
    }, abs=1e-10)


def test_segment_multipliers_defaults_and_shift_cap(balance_sheet):
    segments = pd.DataFrame([
        ["Agriculture", "Bagmati", 100, 0, 0, 0, 0],
        ["Trade", "Koshi", 0, 200, 0, 0, 0],
        ["Services", "Bagmati", 0, 0, 0, 300, 0],
        ["Other", "Lumbini", 0, 0, 0, 0, 50],
    ], columns=["sector", "province", *BUCKETS], index=[5, 2, 9, 1])
    # Shifts .2, capped 2.4 -> 1, .1, .2 respectively.
    result = apply_scenario(segments, balance_sheet, {
        "id": "regional", "base_shift": 0.2,
        "sector_mult": {"Agriculture": 2, "Trade": 3},
        "province_mult": {"Bagmati": 0.5, "Koshi": 4},
    })
    assert result["buckets"] == pytest.approx(dict(zip(BUCKETS, [80, 20, 200, 270, 80], strict=True)))
    assert result["gross_npr"] == 650
    assert result["par30"] == pytest.approx(550 / 650)
    assert result["par90"] == pytest.approx(350 / 650)
    assert result["provisions_npr"] == pytest.approx(266.8)
    assert result["delta_provisions_npr"] == pytest.approx(55.8)
    assert result["capital_npr"] == pytest.approx(444.2)


@pytest.mark.parametrize("shift", [1.0, 2.0])
def test_full_shift_is_simultaneous_and_retains_terminal_bucket(segments, balance_sheet, shift):
    result = apply_scenario(segments, balance_sheet, {"id": "full", "base_shift": shift})
    assert list(result["buckets"].values()) == [0, 100, 200, 300, 900]
    assert result["gross_npr"] == 1500
    assert result["provisions_npr"] == 1105
    assert result["delta_provisions_npr"] == 319


def test_zero_multiplier_prevents_shift(segments, balance_sheet):
    result = apply_scenario(segments, balance_sheet, {
        "id": "none", "base_shift": 1, "sector_mult": {"Agriculture": 0},
    })
    assert list(result["buckets"].values()) == [100, 200, 300, 400, 500]
    assert result["delta_provisions_npr"] == 0


@pytest.mark.parametrize("empty", [False, True])
def test_empty_and_zero_outstanding_segments(segments, balance_sheet, empty):
    if empty:
        segments = segments.iloc[:0]
    else:
        segments.loc[:, BUCKETS] = 0
    balance_sheet["rwa_npr"] = 0
    result = apply_scenario(segments, balance_sheet, {"id": "zero", "base_shift": 0.2, "funding_cost_bps": 200})
    assert list(result["buckets"].values()) == [0] * 5
    assert result["gross_npr"] == result["provisions_npr"] == result["delta_provisions_npr"] == 0
    assert pd.isna(result["par30"]) and pd.isna(result["par90"]) and pd.isna(result["car"])
    assert result["nii_hit_npr"] == 20
    assert result["capital_npr"] == 480
    assert result["liquidity_gap_90d_npr"] == 100


def test_empty_schema_segments(balance_sheet):
    segments = pd.DataFrame(columns=["sector", "province", *BUCKETS])
    result = apply_scenario(segments, balance_sheet, {"id": "empty"})
    assert result["gross_npr"] == 0
    assert result["provisions_npr"] == 0
    assert pd.isna(result["par30"])
    assert result["car"] == 0.25


def test_all_current_shifts_only_to_first_arrears_bucket(balance_sheet):
    segments = pd.DataFrame([["Agriculture", "Bagmati", 1000, 0, 0, 0, 0]], columns=["sector", "province", *BUCKETS])
    result = apply_scenario(segments, balance_sheet, {"id": "current", "base_shift": 0.25})
    assert list(result["buckets"].values()) == [750, 250, 0, 0, 0]
    assert result["par30"] == result["par90"] == 0
    assert result["provisions_npr"] == 20
    assert result["delta_provisions_npr"] == 10


def test_provision_rates_are_configurable(segments, balance_sheet):
    config = {"provision_rates": dict.fromkeys(BUCKETS, 0.1)}
    result = apply_scenario(segments, balance_sheet, {"id": "custom", "base_shift": 0.2}, config)
    assert result["provisions_npr"] == 150
    assert result["delta_provisions_npr"] == 0
    assert result["capital_npr"] == 500


def test_partial_provision_override_uses_defaults_for_other_buckets(segments, balance_sheet):
    result = apply_scenario(segments, balance_sheet, {"id": "custom", "base_shift": 0.2}, {"provision_rates": {"current": 0.02}})
    assert result["provisions_npr"] == pytest.approx(850.6)
    assert result["delta_provisions_npr"] == pytest.approx(63.6)


def test_capital_and_car_are_not_floored(segments, balance_sheet):
    balance_sheet["capital_npr"] = 10
    result = apply_scenario(segments, balance_sheet, {"id": "loss", "funding_cost_bps": 200})
    assert result["capital_npr"] == -10
    assert result["car"] == -0.005


def test_stress_does_not_mutate_inputs(segments, balance_sheet):
    before = segments.copy(deep=True)
    sheet_before = deepcopy(balance_sheet)
    scenario = {"id": "pure", "base_shift": 0.2, "sector_mult": {"Agriculture": 2}}
    scenario_before = deepcopy(scenario)
    config = deepcopy(DEFAULT_CONFIG)
    config_before = deepcopy(config)
    first = apply_scenario(segments, balance_sheet, scenario, config)
    assert first == apply_scenario(segments, balance_sheet, scenario, config)
    pd.testing.assert_frame_equal(segments, before)
    assert balance_sheet == sheet_before
    assert scenario == scenario_before
    assert config == config_before == DEFAULT_CONFIG
