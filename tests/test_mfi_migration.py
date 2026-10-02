"""Opening-weight transition arithmetic, closure and writeoff edge cases."""
from __future__ import annotations

import pandas as pd
import pytest

from cbsrm.mfi import BUCKETS, STATES, migration_matrix, roll_rates
from tests.test_mfi_portfolio import AS_OF, PREV, _loans


@pytest.fixture
def transitions():
    # Opening DPD, opening balance, destination DPD (None = closed), writeoff.
    cases = [
        (0, 100, 30, 0), (0, 200, 0, 0), (0, 300, None, 0), (0, 400, 0, 1),
        (30, 100, 0, 0), (30, 300, 91, 0),
        (90, 200, 181, 0), (90, 300, 31, 0),
        (180, 100, 90, 0), (180, 100, 181, 0),
        (181, 40, 0, 1), (181, 60, 181, 0),
    ]
    rows = []
    for i, (start_dpd, balance, end_dpd, written_off) in enumerate(cases):
        rows.append({"as_of": PREV, "loan_id": str(i), "days_past_due": start_dpd, "outstanding_npr": balance})
        if end_dpd is not None:
            rows.append({"loan_id": str(i), "days_past_due": end_dpd, "outstanding_npr": 0 if written_off else 1, "written_off": written_off})
    # New loans and loans already written off at the start must not affect shares.
    rows.extend([
        {"loan_id": "new", "outstanding_npr": 99999},
        {"as_of": PREV, "loan_id": "old-writeoff", "written_off": 1, "outstanding_npr": 0},
        {"loan_id": "old-writeoff", "outstanding_npr": 100},
    ])
    return _loans(rows)


def test_outstanding_matrix_hand_calculated(transitions):
    result = migration_matrix(transitions, PREV, AS_OF)
    expected = pd.DataFrame([
        [0.2, 0.1, 0, 0, 0, 0.4, 0.3],
        [0.25, 0, 0, 0.75, 0, 0, 0],
        [0, 0, 0.6, 0, 0.4, 0, 0],
        [0, 0, 0.5, 0, 0.5, 0, 0],
        [0, 0, 0, 0, 0.6, 0.4, 0],
    ], index=BUCKETS, columns=STATES, dtype=float)
    pd.testing.assert_frame_equal(result, expected)
    assert result.sum(axis=1).tolist() == pytest.approx([1] * 5)
    assert roll_rates(result).tolist() == pytest.approx([0.5, 0.75, 0.4, 0.5, 0.4])


def test_count_matrix_hand_calculated(transitions):
    result = migration_matrix(transitions, PREV, AS_OF, weight="count")
    expected = pd.DataFrame([
        [0.25, 0.25, 0, 0, 0, 0.25, 0.25],
        [0.5, 0, 0, 0.5, 0, 0, 0],
        [0, 0, 0.5, 0, 0.5, 0, 0],
        [0, 0, 0.5, 0, 0.5, 0, 0],
        [0, 0, 0, 0, 0.5, 0.5, 0],
    ], index=BUCKETS, columns=STATES, dtype=float)
    pd.testing.assert_frame_equal(result, expected)
    assert roll_rates(result).tolist() == pytest.approx([0.5] * 5)


@pytest.mark.parametrize("weight", ["outstanding", "count"])
def test_empty_opening_snapshot(weight):
    matrix = migration_matrix(_loans([]), PREV, AS_OF, weight=weight)
    assert list(matrix.index) == BUCKETS
    assert list(matrix.columns) == STATES
    assert matrix.isna().all().all()
    assert roll_rates(matrix).isna().all()


def test_new_loans_only_have_no_opening_weight():
    matrix = migration_matrix(_loans([{}]), PREV, AS_OF)
    assert matrix.isna().all().all()


def test_zero_outstanding_is_nan_but_count_weight_is_one():
    loans = _loans([
        {"as_of": PREV, "outstanding_npr": 0},
        {"outstanding_npr": 0, "written_off": 1},
    ])
    matrix = migration_matrix(loans, PREV, AS_OF)
    assert matrix.isna().all().all()
    counted = migration_matrix(loans, PREV, AS_OF, weight="count")
    assert counted.loc["current", "written_off"] == 1
    assert roll_rates(counted)["current"] == 1
    assert counted.loc[BUCKETS[1:]].isna().all().all()


@pytest.mark.parametrize("weight", ["outstanding", "count"])
def test_all_current_and_unobserved_buckets(weight):
    loans = _loans([
        {"as_of": date, "loan_id": loan_id, "outstanding_npr": amount}
        for date in [PREV, AS_OF] for loan_id, amount in [("A", 100), ("B", 200)]
    ])
    matrix = migration_matrix(loans, PREV, AS_OF, weight=weight)
    assert matrix.loc["current"].tolist() == [1, 0, 0, 0, 0, 0, 0]
    assert matrix.loc[BUCKETS[1:]].isna().all().all()
    rates = roll_rates(matrix)
    assert rates["current"] == 0
    assert rates[BUCKETS[1:]].isna().all()


def test_loans_closed_between_dates_are_not_worse():
    loans = _loans([
        {"as_of": PREV, "loan_id": str(i), "days_past_due": dpd}
        for i, dpd in enumerate([0, 1, 31, 91, 181])
    ])
    matrix = migration_matrix(loans, PREV, AS_OF)
    assert matrix["closed"].tolist() == [1] * 5
    assert matrix[STATES[:-1]].eq(0).all().all()
    assert roll_rates(matrix).tolist() == [0] * 5


def test_zero_balance_at_destination_is_still_a_bucket_when_present():
    loans = _loans([{"as_of": PREV}, {"outstanding_npr": 0}])
    matrix = migration_matrix(loans, PREV, AS_OF)
    assert matrix.loc["current", "current"] == 1
    assert matrix.loc["current", "closed"] == 0


def test_same_date_is_identity_for_observed_buckets(transitions):
    matrix = migration_matrix(transitions, PREV, PREV)
    expected = pd.DataFrame(0.0, index=BUCKETS, columns=STATES)
    for bucket in BUCKETS:
        expected.loc[bucket, bucket] = 1.0
    pd.testing.assert_frame_equal(matrix, expected)


def test_invalid_weight_rejected(transitions):
    with pytest.raises(ValueError, match="weight"):
        migration_matrix(transitions, PREV, AS_OF, weight="closing_balance")


def test_migration_and_roll_rates_do_not_mutate_inputs(transitions):
    before = transitions.copy(deep=True)
    first = migration_matrix(transitions, PREV, AS_OF)
    matrix_before = first.copy(deep=True)
    roll_rates(first)
    pd.testing.assert_frame_equal(first, matrix_before)
    pd.testing.assert_frame_equal(transitions, before)
    pd.testing.assert_frame_equal(first, migration_matrix(transitions.sample(frac=1, random_state=42), PREV, AS_OF))
