"""Configurable five-band classification (contract addendum v1.1, section 3).

Hand-built frames only. Bands and rates are placeholders pending calibration.
"""
from __future__ import annotations

import math
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from cbsrm.mfi import (
    DEFAULT_CLASSIFICATION,
    assign_class,
    classification_table,
    validate_classification,
)

AS_OF = "2026-02-28"
PREV = "2026-01-31"
COLUMNS = [
    "key", "label", "min_dpd", "max_dpd", "n_loans", "balance_npr", "share",
    "provision_rate", "provision_npr",
]
KEYS = ["pass", "watchlist", "substandard", "doubtful", "loss"]
DEFAULT_SNAPSHOT = deepcopy(DEFAULT_CLASSIFICATION)


def _loans(rows: list[dict]) -> pd.DataFrame:
    """Fill the complete contract schema, including for an empty input."""
    defaults = {
        "as_of": AS_OF, "loan_id": "L1", "branch_id": "BR001", "branch_name": "Sample",
        "district": "Kathmandu", "province": "Bagmati", "product": "Group",
        "sector": "Agriculture", "disbursed_npr": 1000.0, "outstanding_npr": 100.0,
        "days_past_due": 0, "restructured": 0, "written_off": 0, "writeoff_npr": 0.0,
        "due_npr": 100.0, "collected_npr": 100.0,
    }
    return pd.DataFrame([{**defaults, **row} for row in rows], columns=list(defaults))


def _band(key, low, high, rate, label=None):
    return {"key": key, "label": label or key.title(), "min_dpd": low, "max_dpd": high,
            "provision_rate": rate}


def _config(*bands) -> dict:
    return {"bands": list(bands)}


def _default_with(position: int, **changes) -> dict:
    config = deepcopy(DEFAULT_CLASSIFICATION)
    config["bands"][position].update(changes)
    return config


THREE_BANDS = _config(
    _band("performing", 0, 0, 0.02),
    _band("overdue", 1, 59, 0.2),
    _band("default", 60, None, 0.9),
)


@pytest.fixture
def book() -> pd.DataFrame:
    """One live loan at every default boundary, plus rows that must be ignored."""
    return _loans([
        {"loan_id": "A", "outstanding_npr": 1000.0, "days_past_due": 0},
        {"loan_id": "B", "outstanding_npr": 200.0, "days_past_due": 30},
        {"loan_id": "C", "outstanding_npr": 300.0, "days_past_due": 31},
        {"loan_id": "D", "outstanding_npr": 400.0, "days_past_due": 90},
        {"loan_id": "E", "outstanding_npr": 500.0, "days_past_due": 91},
        {"loan_id": "F", "outstanding_npr": 600.0, "days_past_due": 180},
        {"loan_id": "G", "outstanding_npr": 700.0, "days_past_due": 181},
        {"loan_id": "H", "outstanding_npr": 800.0, "days_past_due": 365},
        {"loan_id": "I", "outstanding_npr": 900.0, "days_past_due": 366},
        {"loan_id": "J", "outstanding_npr": 100.0, "days_past_due": 10000},
        # Written off: excluded even with a (contract-breaking) balance and any dpd.
        {"loan_id": "W1", "written_off": 1, "outstanding_npr": 0.0, "days_past_due": 400,
         "writeoff_npr": 50.0},
        {"loan_id": "W2", "written_off": 1, "outstanding_npr": 7777.0, "days_past_due": 0},
        # Another month-end: excluded.
        {"loan_id": "OLD", "as_of": PREV, "outstanding_npr": 9999.0, "days_past_due": 500},
    ])


# ---------------------------------------------------------------- defaults


def test_default_matches_addendum_exactly():
    assert DEFAULT_CLASSIFICATION == {"bands": [
        {"key": "pass", "label": "Pass", "min_dpd": 0, "max_dpd": 30,
         "provision_rate": 0.01},
        {"key": "watchlist", "label": "Watchlist", "min_dpd": 31, "max_dpd": 90,
         "provision_rate": 0.05},
        {"key": "substandard", "label": "Substandard", "min_dpd": 91, "max_dpd": 180,
         "provision_rate": 0.25},
        {"key": "doubtful", "label": "Doubtful", "min_dpd": 181, "max_dpd": 365,
         "provision_rate": 0.50},
        {"key": "loss", "label": "Loss", "min_dpd": 366, "max_dpd": None,
         "provision_rate": 1.00},
    ]}


def test_default_is_valid_and_documented_as_placeholder():
    import cbsrm.mfi.classification as module

    assert validate_classification(DEFAULT_CLASSIFICATION) == []
    assert "placeholders pending calibration" in module.__doc__
    assert "NOT NRB values" in module.__doc__


# ---------------------------------------------------------------- assign_class


@pytest.mark.parametrize("dpd, expected", [
    (0, "pass"), (30, "pass"), (31, "watchlist"), (90, "watchlist"),
    (91, "substandard"), (180, "substandard"), (181, "doubtful"), (365, "doubtful"),
    (366, "loss"), (10000, "loss"),
])
def test_assign_class_default_boundaries(dpd, expected):
    source = pd.Series([dpd], index=["loan"], name="dpd")
    result = assign_class(source)
    assert result.loc["loan"] == expected
    assert result.name == "dpd"
    assert list(result.index) == ["loan"]
    pd.testing.assert_series_equal(source, pd.Series([dpd], index=["loan"], name="dpd"))


def test_assign_class_is_ordered_categorical_in_band_order():
    result = assign_class(pd.Series([400, 0, 95, 31, 200]))
    assert isinstance(result.dtype, pd.CategoricalDtype)
    assert result.cat.ordered
    assert list(result.cat.categories) == KEYS
    assert result.tolist() == ["loss", "pass", "substandard", "watchlist", "doubtful"]
    assert result.max() == "loss" and result.min() == "pass"


@pytest.mark.parametrize("values", [
    [0, 30, 31, 366],
    [0.0, 30.0, 31.0, 366.0],
    np.array([0, 30, 31, 366], dtype=np.int32),
])
def test_assign_class_accepts_int_float_and_numpy_inputs(values):
    result = assign_class(pd.Series(values))
    assert result.tolist() == ["pass", "pass", "watchlist", "loss"]


def test_assign_class_values_in_no_band_are_missing():
    # Negative, missing, and a fraction falling between two integer bands.
    result = assign_class(pd.Series([-1, np.nan, 30.5, 31]))
    assert result.isna().tolist() == [True, True, True, False]
    assert result.iloc[3] == "watchlist"


def test_assign_class_values_that_are_not_numbers_are_missing():
    # Same rule as the site engine: only numbers are placed, text is not converted.
    values = pd.Series([None, "", "31", True, False, 31, np.int64(91), 10**400], dtype=object)
    result = assign_class(values)
    assert result.isna().tolist() == [True] * 5 + [False] * 3
    assert result.iloc[5:].tolist() == ["watchlist", "substandard", "loss"]
    assert assign_class(pd.Series([True, False])).isna().all()
    assert assign_class(pd.Series([True, None], dtype="boolean")).isna().all()
    assert assign_class(pd.Series(["0", "31"])).isna().all()


def test_assign_class_nullable_integers_and_infinity():
    result = assign_class(pd.Series([0, pd.NA, 400], dtype="Int64"))
    assert result.isna().tolist() == [False, True, False]
    assert assign_class(pd.Series([np.inf, -np.inf])).tolist()[0] == "loss"
    assert assign_class(pd.Series([-np.inf])).isna().all()


def test_assign_class_empty():
    result = assign_class(pd.Series([], dtype="int64"))
    assert result.empty
    assert list(result.cat.categories) == KEYS


def test_assign_class_custom_three_bands():
    result = assign_class(pd.Series([0, 1, 59, 60, 5000]), THREE_BANDS)
    assert result.tolist() == ["performing", "overdue", "overdue", "default", "default"]
    assert list(result.cat.categories) == ["performing", "overdue", "default"]


def test_assign_class_single_open_band_takes_everything():
    config = _config(_band("all", 0, None, 0.1))
    assert assign_class(pd.Series([0, 1, 10**6]), config).tolist() == ["all"] * 3


def test_assign_class_single_day_band():
    config = _config(_band("zero", 0, 0, 0.0), _band("rest", 1, None, 1.0))
    assert assign_class(pd.Series([0, 1, 2]), config).tolist() == ["zero", "rest", "rest"]


def test_assign_class_none_config_means_default():
    values = pd.Series([0, 31, 91, 181, 366])
    pd.testing.assert_series_equal(
        assign_class(values, None), assign_class(values, DEFAULT_CLASSIFICATION))


def test_assign_class_rejects_invalid_config_with_readable_problems():
    config = _default_with(1, min_dpd=32, provision_rate=2)
    with pytest.raises(ValueError) as excinfo:
        assign_class(pd.Series([0]), config)
    message = str(excinfo.value)
    assert message.startswith("Invalid classification config: ")
    for problem in validate_classification(config):
        assert problem in message


# ---------------------------------------------------------------- classification_table


def test_table_columns_order_and_dtypes(book):
    table = classification_table(book, AS_OF)
    assert list(table.columns) == COLUMNS
    assert table["key"].tolist() == KEYS
    assert table["label"].tolist() == ["Pass", "Watchlist", "Substandard", "Doubtful", "Loss"]
    assert list(table.index) == [0, 1, 2, 3, 4]
    assert table["min_dpd"].tolist() == [0, 31, 91, 181, 366]
    assert table["max_dpd"].dtype == object
    assert table["max_dpd"].tolist() == [30, 90, 180, 365, None]
    assert table["max_dpd"].iloc[-1] is None
    assert all(type(v) is int for v in table["max_dpd"].iloc[:-1])
    for column in ("min_dpd", "n_loans"):
        assert pd.api.types.is_integer_dtype(table[column])
    for column in ("balance_npr", "share", "provision_rate", "provision_npr"):
        assert pd.api.types.is_float_dtype(table[column])


def test_table_hand_calculated(book):
    table = classification_table(book, AS_OF)
    # Live balances: pass 1000+200, watchlist 300+400, substandard 500+600,
    # doubtful 700+800, loss 900+100. Gross 5500.
    assert table["n_loans"].tolist() == [2, 2, 2, 2, 2]
    assert table["balance_npr"].tolist() == [1200.0, 700.0, 1100.0, 1500.0, 1000.0]
    assert table["share"].tolist() == pytest.approx(
        [1200 / 5500, 700 / 5500, 1100 / 5500, 1500 / 5500, 1000 / 5500], abs=1e-15)
    assert table["provision_rate"].tolist() == [0.01, 0.05, 0.25, 0.50, 1.0]
    assert table["provision_npr"].tolist() == pytest.approx([12.0, 35.0, 275.0, 750.0, 1000.0])


def test_table_provision_totals(book):
    table = classification_table(book, AS_OF)
    assert table["balance_npr"].sum() == 5500.0
    assert table["share"].sum() == pytest.approx(1.0, abs=1e-12)
    assert table["provision_npr"].sum() == pytest.approx(12 + 35 + 275 + 750 + 1000)
    assert (table["provision_npr"] == table["balance_npr"] * table["provision_rate"]).all()


def test_table_excludes_written_off_rows_and_other_dates(book):
    table = classification_table(book, AS_OF)
    assert table["n_loans"].sum() == 10
    live_only = book.loc[(book["written_off"] == 0) & (book["as_of"] == AS_OF)]
    pd.testing.assert_frame_equal(table, classification_table(live_only, AS_OF))
    previous = classification_table(book, PREV)
    assert previous["n_loans"].tolist() == [0, 0, 0, 0, 1]
    assert previous["balance_npr"].tolist() == [0, 0, 0, 0, 9999.0]
    assert previous["share"].tolist() == [0, 0, 0, 0, 1.0]


def test_table_only_written_off_rows_gives_zeros_and_nan_share():
    loans = _loans([{"written_off": 1, "outstanding_npr": 0.0, "writeoff_npr": 80.0}])
    table = classification_table(loans, AS_OF)
    assert table["n_loans"].tolist() == [0] * 5
    assert table["share"].isna().all()


def test_table_bands_without_rows_are_present_with_zeros():
    loans = _loans([{"loan_id": "A", "outstanding_npr": 50.0, "days_past_due": 100}])
    table = classification_table(loans, AS_OF)
    assert table["key"].tolist() == KEYS
    assert table["n_loans"].tolist() == [0, 0, 1, 0, 0]
    assert table["balance_npr"].tolist() == [0, 0, 50.0, 0, 0]
    assert table["share"].tolist() == [0, 0, 1.0, 0, 0]
    assert table["provision_npr"].tolist() == [0, 0, 12.5, 0, 0]


@pytest.mark.parametrize("loans, date", [
    (_loans([{"outstanding_npr": 10.0}]), "1900-01-31"),  # date absent
    (_loans([]), AS_OF),                                  # empty schema frame
])
def test_table_empty_date_gives_zeros_and_nan_share(loans, date):
    table = classification_table(loans, date)
    assert list(table.columns) == COLUMNS
    assert table["key"].tolist() == KEYS
    assert table["n_loans"].tolist() == [0] * 5
    assert table["balance_npr"].tolist() == [0.0] * 5
    assert table["provision_npr"].tolist() == [0.0] * 5
    assert table["share"].isna().all()
    assert table["max_dpd"].tolist() == [30, 90, 180, 365, None]
    assert pd.api.types.is_integer_dtype(table["n_loans"])


def test_table_zero_gross_with_live_rows_counts_loans_and_nan_share():
    loans = _loans([{"loan_id": "A", "outstanding_npr": 0.0, "days_past_due": 45},
                    {"loan_id": "B", "outstanding_npr": 0.0, "days_past_due": 0}])
    table = classification_table(loans, AS_OF)
    assert table["n_loans"].tolist() == [1, 1, 0, 0, 0]
    assert table["share"].isna().all()
    assert table["provision_npr"].tolist() == [0.0] * 5


def test_table_custom_three_bands(book):
    table = classification_table(book, AS_OF, THREE_BANDS)
    assert table["key"].tolist() == ["performing", "overdue", "default"]
    assert table["label"].tolist() == ["Performing", "Overdue", "Default"]
    assert table["min_dpd"].tolist() == [0, 1, 60]
    assert table["max_dpd"].tolist() == [0, 59, None]
    # performing: A (dpd 0); overdue: B, C (30, 31); default: the other seven.
    assert table["n_loans"].tolist() == [1, 2, 7]
    assert table["balance_npr"].tolist() == [1000.0, 500.0, 4000.0]
    assert table["share"].tolist() == pytest.approx([1000 / 5500, 500 / 5500, 4000 / 5500])
    assert table["provision_npr"].tolist() == pytest.approx([20.0, 100.0, 3600.0])


def test_table_custom_cutoffs_shift_boundary_loans(book):
    config = _config(
        _band("early", 0, 29, 0.0),
        _band("mid", 30, 90, 0.5),
        _band("late", 91, 366, 0.75),
        _band("written", 367, None, 1.0, label="Beyond a year"),
    )
    table = classification_table(book, AS_OF, config)
    assert table["n_loans"].tolist() == [1, 3, 5, 1]
    assert table["balance_npr"].tolist() == [1000.0, 900.0, 3500.0, 100.0]
    assert table["label"].tolist() == ["Early", "Mid", "Late", "Beyond a year"]
    assert table["provision_npr"].sum() == pytest.approx(0 + 450 + 2625 + 100)


def test_table_label_falls_back_to_key():
    config = {"bands": [
        {"key": "ok", "min_dpd": 0, "max_dpd": 9, "provision_rate": 0.0},
        {"key": "late", "label": None, "min_dpd": 10, "max_dpd": 19, "provision_rate": 0.1},
        {"key": "later", "label": "", "min_dpd": 20, "max_dpd": 29, "provision_rate": 0.2},
        {"key": "latest", "label": " \t\ufeff", "min_dpd": 30, "max_dpd": 39,
         "provision_rate": 0.3},
        {"key": "bad", "label": 5, "min_dpd": 40, "max_dpd": None, "provision_rate": 1.0},
    ]}
    assert validate_classification(config) == []
    table = classification_table(_loans([]), AS_OF, config)
    assert table["label"].tolist() == ["ok", "late", "later", "latest", "bad"]
    kept = _config(_band("a", 0, None, 0.5, label=" Kept as written "))
    assert classification_table(_loans([]), AS_OF, kept)["label"].tolist() == [" Kept as written "]


def test_table_whole_float_and_numpy_cutoffs_are_normalised():
    config = _config(
        _band("a", 0.0, np.int64(30), 0.5),
        _band("b", np.int64(31), None, np.float64(1.0)),
    )
    table = classification_table(_loans([{"days_past_due": 31}]), AS_OF, config)
    assert table["min_dpd"].tolist() == [0, 31]
    assert table["max_dpd"].tolist() == [30, None]
    assert all(type(v) is int for v in table["max_dpd"].iloc[:-1])
    assert table["n_loans"].tolist() == [0, 1]


def test_table_rejects_invalid_config(book):
    with pytest.raises(ValueError, match="Band 5"):
        classification_table(book, AS_OF, _default_with(4, max_dpd=1000))
    with pytest.raises(ValueError, match="At least one band is needed"):
        classification_table(book, AS_OF, {"bands": []})


def test_table_json_round_trip_uses_null_for_open_band(book):
    records = classification_table(_loans([]), AS_OF).to_dict("records")
    assert records[-1]["max_dpd"] is None
    assert math.isnan(records[0]["share"])
    assert classification_table(book, AS_OF).to_dict("records")[0]["max_dpd"] == 30


# ---------------------------------------------------------------- validate_classification


def test_validate_accepts_edge_values():
    config = _config(
        _band("zero", 0, 0, 0),        # single-day band, integer rate 0
        _band("one", 1, 1, 1),         # integer rate 1
        _band("rest", 2, None, 1.0),
    )
    assert validate_classification(config) == []
    assert validate_classification(_config(_band("only", 0, None, 0.5))) == []
    assert validate_classification({"bands": tuple(THREE_BANDS["bands"])}) == []


@pytest.mark.parametrize("config, expected", [
    (None, ['The classification settings must be an object with a "bands" list.']),
    ([], ['The classification settings must be an object with a "bands" list.']),
    ("bands", ['The classification settings must be an object with a "bands" list.']),
    ({}, ['The classification settings need a "bands" list.']),
    ({"bands": None}, ['The classification settings need a "bands" list.']),
    ({"bands": {"pass": {}}}, ['The classification settings need a "bands" list.']),
    ({"bands": "pass"}, ['The classification settings need a "bands" list.']),
    ({"bands": []}, ["At least one band is needed."]),
])
def test_validate_top_level_problems(config, expected):
    assert validate_classification(config) == expected


BAND_OBJECT = "must be an object with key, label, min_dpd, max_dpd and provision_rate."
RATE = "provision_rate must be a number from 0 to 1 (for example 0.25 for 25%)."
MIN = "min_dpd must be a whole number of days, 0 or more."
MAX = "max_dpd must be a whole number of days, 0 or more, or empty for no upper limit."


@pytest.mark.parametrize("position, changes, expected", [
    # key
    (1, {"key": None}, ['Band 2 needs a key, a short name such as "pass".']),
    (1, {"key": ""}, ['Band 2 needs a key, a short name such as "pass".']),
    (1, {"key": "   "}, ['Band 2 needs a key, a short name such as "pass".']),
    (1, {"key": 7}, ['Band 2 needs a key, a short name such as "pass".']),
    (1, {"key": "\ufeff\u3000"}, ['Band 2 needs a key, a short name such as "pass".']),
    (2, {"key": "pass"},
     ['Band 3 ("pass") uses the same key as band 1. Each band needs a different key.']),
    # min_dpd
    (1, {"min_dpd": None}, [f'Band 2 ("watchlist"): {MIN}']),
    (1, {"min_dpd": "31"}, [f'Band 2 ("watchlist"): {MIN}']),
    (1, {"min_dpd": True}, [f'Band 2 ("watchlist"): {MIN}']),
    (1, {"min_dpd": 31.5}, [f'Band 2 ("watchlist"): {MIN}']),
    (1, {"min_dpd": float("nan")}, [f'Band 2 ("watchlist"): {MIN}']),
    (0, {"min_dpd": -1}, [f'Band 1 ("pass"): {MIN}']),
    (0, {"min_dpd": 1},
     ['Band 1 ("pass") must start at 0 days past due, but its min_dpd is 1.']),
    (1, {"min_dpd": 32},
     ['Band 2 ("watchlist") must start at 31 days past due, one day after band 1 ends, '
      'but its min_dpd is 32.']),
    (1, {"min_dpd": 30},
     ['Band 2 ("watchlist") must start at 31 days past due, one day after band 1 ends, '
      'but its min_dpd is 30.']),
    # max_dpd
    (1, {"max_dpd": "90"}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": -5}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": 90.5}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": float("inf")}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": False}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": 1e21}, [f'Band 2 ("watchlist"): {MAX}']),
    (1, {"max_dpd": 10**400}, [f'Band 2 ("watchlist"): {MAX}']),
    (2, {"max_dpd": None},
     ['Band 3 ("substandard") has no upper limit (empty max_dpd), but only the last band '
      'may be open-ended.']),
    (4, {"max_dpd": 999},
     ['Band 5 ("loss") is the last band, so its max_dpd must be empty (no upper limit) so '
      'that every loan falls in a band.']),
    (4, {"max_dpd": 365},
     ['Band 5 ("loss") is the last band, so its max_dpd must be empty (no upper limit) so '
      'that every loan falls in a band.',
      'Band 5 ("loss") ends at 365 days past due, before it starts at 366. max_dpd must be '
      'at least min_dpd.']),
    # provision_rate
    (1, {"provision_rate": None}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": -0.01}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": 1.01}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": "0.05"}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": True}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": float("nan")}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": 10**400}, [f'Band 2 ("watchlist"): {RATE}']),
    (1, {"provision_rate": np.True_}, [f'Band 2 ("watchlist"): {RATE}']),
])
def test_validate_band_problems(position, changes, expected):
    assert validate_classification(_default_with(position, **changes)) == expected


def test_validate_day_limits_stop_at_the_largest_exact_javascript_whole_number():
    top = 2**53 - 1
    config = _config(_band("a", 0, top - 1, 0.1), _band("b", top, None, 0.2))
    assert validate_classification(config) == []
    table = classification_table(_loans([{"days_past_due": 10**6}]), AS_OF, config)
    assert table["min_dpd"].tolist() == [0, top]
    assert table["max_dpd"].tolist() == [top - 1, None]
    assert table["n_loans"].tolist() == [1, 0]
    too_far = _config(_band("a", 0, top, 0.1), _band("b", top + 1, None, 0.2))
    assert validate_classification(too_far) == [f'Band 2 ("b"): {MIN}']


def test_validate_max_before_min_in_middle_band():
    config = _config(_band("a", 0, 10, 0.1), _band("b", 11, 5, 0.2), _band("c", 6, None, 1.0))
    assert validate_classification(config) == [
        'Band 2 ("b") ends at 5 days past due, before it starts at 11. max_dpd must be at '
        "least min_dpd.",
    ]


def test_validate_missing_fields_and_non_object_band():
    config = {"bands": [{"key": "pass"}, "watchlist", {"min_dpd": 0, "max_dpd": None}]}
    assert validate_classification(config) == [
        f'Band 1 ("pass"): {MIN}',
        'Band 1 ("pass") has no upper limit (empty max_dpd), but only the last band may be '
        "open-ended.",
        f'Band 1 ("pass"): {RATE}',
        f"Band 2 {BAND_OBJECT}",
        'Band 3 needs a key, a short name such as "pass".',
        f"Band 3: {RATE}",
    ]


def test_validate_reports_every_problem_in_band_order():
    config = _config(
        _band("a", 1, 3, 2),
        _band("a", 5, None, 0.5),
        _band("c", 4, 2, 0.5),
    )
    assert validate_classification(config) == [
        'Band 1 ("a") must start at 0 days past due, but its min_dpd is 1.',
        f'Band 1 ("a"): {RATE}',
        'Band 2 ("a") uses the same key as band 1. Each band needs a different key.',
        'Band 2 ("a") must start at 4 days past due, one day after band 1 ends, but its '
        "min_dpd is 5.",
        'Band 2 ("a") has no upper limit (empty max_dpd), but only the last band may be '
        "open-ended.",
        'Band 3 ("c") is the last band, so its max_dpd must be empty (no upper limit) so that '
        "every loan falls in a band.",
        'Band 3 ("c") ends at 2 days past due, before it starts at 4. max_dpd must be at '
        "least min_dpd.",
    ]


def test_validate_messages_are_plain_sentences():
    config = {"bands": [7, {"key": "", "min_dpd": "x", "max_dpd": "y", "provision_rate": 9}]}
    problems = validate_classification(config)
    assert len(problems) == 5
    for problem in problems:
        assert problem.startswith("Band ") and problem.endswith(".")
        assert "Traceback" not in problem and "None" not in problem


# ---------------------------------------------------------------- purity


def test_calls_do_not_mutate_defaults_configs_or_inputs(book):
    before = book.copy(deep=True)
    config = deepcopy(THREE_BANDS)
    validate_classification(DEFAULT_CLASSIFICATION)
    assign_class(book["days_past_due"])
    assign_class(book["days_past_due"], config)
    table = classification_table(book, AS_OF)
    classification_table(book, AS_OF, config)
    classification_table(book, "1900-01-31")
    # Editing a returned table must not reach the shared default.
    table.loc[0, "provision_rate"] = 0.99
    table.loc[4, "max_dpd"] = 1
    with pytest.raises(ValueError):
        classification_table(book, AS_OF, _default_with(0, provision_rate=5))
    assert DEFAULT_CLASSIFICATION == DEFAULT_SNAPSHOT
    assert config == THREE_BANDS
    pd.testing.assert_frame_equal(book, before)
    assert classification_table(book, AS_OF)["provision_rate"].iloc[0] == 0.01


def test_missing_max_dpd_key_is_open_ended_like_the_js_engine():
    """A band with no max_dpd key validates like max_dpd=None and must not crash."""
    cfg = {"bands": [
        {"key": "a", "label": "A", "min_dpd": 0, "max_dpd": 30, "provision_rate": 0.1},
        {"key": "b", "label": "B", "min_dpd": 31, "provision_rate": 1.0},
    ]}
    assert validate_classification(cfg) == []
    assert list(assign_class(pd.Series([0, 31, 400]), cfg)) == ["a", "b", "b"]
    frame = pd.DataFrame({"as_of": ["2026-09-30"] * 2, "written_off": [0, 0],
                          "outstanding_npr": [100.0, 50.0], "days_past_due": [0, 400]})
    table = classification_table(frame, "2026-09-30", cfg)
    assert table["max_dpd"].tolist() == [30, None]
    assert table["balance_npr"].tolist() == [100.0, 50.0]
