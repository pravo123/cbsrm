"""Hand-calculated branch rules, inclusive thresholds and severity boundaries."""
from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from cbsrm.mfi import DEFAULT_CONFIG, branch_alerts
from tests.test_mfi_portfolio import AS_OF, PREV, _loans

ALERT_COLUMNS = ["branch_id", "rule", "value", "threshold", "severity"]
RULES = {
    "PAR30_LEVEL": "par30_level", "PAR30_JUMP": "par30_jump",
    "ROLL_RATE": "roll_rate", "COLLECTION_DROP": "collection_drop",
}


def _threshold_loans(affected: float) -> pd.DataFrame:
    return _loans([
        {"as_of": PREV, "loan_id": "A", "outstanding_npr": affected, "due_npr": 1000, "collected_npr": 1000},
        {"as_of": PREV, "loan_id": "B", "outstanding_npr": 1000 - affected, "due_npr": 0, "collected_npr": 0},
        {"loan_id": "A", "outstanding_npr": affected, "days_past_due": 31, "due_npr": 1000, "collected_npr": 1000 - affected},
        {"loan_id": "B", "outstanding_npr": 1000 - affected, "due_npr": 0, "collected_npr": 0},
    ])


def test_four_rules_hand_calculated_and_sorted():
    rows = []
    for date in [PREV, AS_OF]:
        # BR001: PAR=.10 both dates; 50/900 of current rolls; collection drop=1/16.
        for loan_id, balance, dpd in [("A", 100, 31), ("B", 50, 1 if date == AS_OF else 0), ("C", 850, 0)]:
            rows.append({"as_of": date, "branch_id": "BR001", "loan_id": loan_id, "outstanding_npr": balance, "days_past_due": dpd, "due_npr": 16, "collected_npr": 15 if date == AS_OF else 16})
        # BR002: PAR rises from 0 to .20; .20 rolls; collection drop=.25.
        for loan_id, balance, dpd in [("D", 200, 91 if date == AS_OF else 0), ("E", 800, 0)]:
            rows.append({"as_of": date, "branch_id": "BR002", "loan_id": loan_id, "outstanding_npr": balance, "days_past_due": dpd, "due_npr": 4, "collected_npr": 3 if date == AS_OF else 4})
        rows.append({"as_of": date, "branch_id": "BR003", "loan_id": "F"})
    loans = _loans(rows).sample(frac=1, random_state=11)
    expected = pd.DataFrame([
        ["BR001", "COLLECTION_DROP", 1 / 16, 0.05, "medium"],
        ["BR001", "PAR30_LEVEL", 0.1, 0.1, "medium"],
        ["BR001", "ROLL_RATE", 1 / 18, 0.05, "medium"],
        ["BR002", "COLLECTION_DROP", 0.25, 0.05, "high"],
        ["BR002", "PAR30_JUMP", 0.2, 0.02, "high"],
        ["BR002", "PAR30_LEVEL", 0.2, 0.1, "high"],
        ["BR002", "ROLL_RATE", 0.2, 0.05, "high"],
    ], columns=ALERT_COLUMNS)
    pd.testing.assert_frame_equal(branch_alerts(loans, AS_OF, PREV), expected)


@pytest.mark.parametrize("rule", list(RULES))
@pytest.mark.parametrize("affected, severity", [(124, None), (125, "medium"), (249, "medium"), (250, "high")])
def test_threshold_and_double_threshold_are_inclusive(rule, affected, severity):
    # Binary-exact threshold avoids decimal subtraction artifacts at equality.
    thresholds = dict.fromkeys(RULES.values(), 10.0)
    thresholds[RULES[rule]] = 0.125
    result = branch_alerts(_threshold_loans(affected), AS_OF, PREV, {"alerts": thresholds})
    if severity is None:
        assert result.empty
        assert list(result.columns) == ALERT_COLUMNS
    else:
        assert len(result) == 1
        row = result.iloc[0]
        assert row["rule"] == rule
        assert row["value"] == pytest.approx(affected / 1000)
        assert row["threshold"] == 0.125
        assert row["severity"] == severity


def test_partial_config_override_keeps_other_default_rules():
    result = branch_alerts(_threshold_loans(125), AS_OF, PREV, {"alerts": {"par30_level": 0.5}})
    assert result["rule"].tolist() == ["COLLECTION_DROP", "PAR30_JUMP", "ROLL_RATE"]
    assert result["threshold"].tolist() == [0.05, 0.02, 0.05]


def test_roll_rate_uses_opening_weights_and_counts_written_off():
    loans = _loans([
        {"as_of": PREV, "loan_id": "A", "outstanding_npr": 10},
        {"as_of": PREV, "loan_id": "B", "outstanding_npr": 90},
        {"loan_id": "A", "written_off": 1, "outstanding_npr": 0},
        {"loan_id": "B", "outstanding_npr": 1},
    ])
    result = branch_alerts(loans, AS_OF, PREV)
    assert result["rule"].tolist() == ["ROLL_RATE"]
    assert result.iloc[0]["value"] == 0.1
    assert result.iloc[0]["severity"] == "high"


@pytest.mark.parametrize("rows", [
    [],
    [{"as_of": PREV}, {}],  # All current, stable collection.
    [{"as_of": PREV, "outstanding_npr": 0, "due_npr": 0}, {"outstanding_npr": 0, "due_npr": 0}],
    [{"as_of": PREV}],  # Entire branch closed; closure is not deterioration.
    [{"as_of": PREV, "written_off": 1, "outstanding_npr": 0}, {"written_off": 1, "outstanding_npr": 0}],
])
def test_empty_zero_all_current_closed_and_written_off_branches(rows):
    result = branch_alerts(_loans(rows), AS_OF, PREV)
    assert result.empty
    assert list(result.columns) == ALERT_COLUMNS


def test_nan_values_never_fire_even_at_zero_threshold():
    loans = _loans([
        {"as_of": date, "outstanding_npr": 0, "due_npr": 0, "collected_npr": 0}
        for date in [PREV, AS_OF]
    ])
    assert branch_alerts(loans, AS_OF, PREV, {"alerts": dict.fromkeys(RULES.values(), 0)}).empty


def test_new_branch_has_level_but_no_previous_period_alerts():
    result = branch_alerts(_loans([{"days_past_due": 31}]), AS_OF, PREV)
    assert result["rule"].tolist() == ["PAR30_LEVEL"]
    assert result.iloc[0]["value"] == 1


def test_improvement_does_not_fire_jump_roll_or_collection_drop():
    loans = _loans([
        {"as_of": PREV, "days_past_due": 31, "collected_npr": 50},
        {"days_past_due": 0, "collected_npr": 100},
    ])
    assert branch_alerts(loans, AS_OF, PREV).empty


def test_alerts_do_not_mutate_inputs():
    loans = _threshold_loans(125)
    before = loans.copy(deep=True)
    config = deepcopy(DEFAULT_CONFIG)
    original = deepcopy(config)
    first = branch_alerts(loans, AS_OF, PREV, config)
    pd.testing.assert_frame_equal(first, branch_alerts(loans, AS_OF, PREV, config))
    pd.testing.assert_frame_equal(loans, before)
    assert config == original == DEFAULT_CONFIG
