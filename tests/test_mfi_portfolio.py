"""Hand-calculated balances, boundary cases and purity for contract v1."""
from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from cbsrm.mfi import BUCKETS, DEFAULT_CONFIG, assign_bucket, bucket_balances, portfolio_metrics

AS_OF = "2026-02-28"
PREV = "2026-01-31"
METRICS = [
    "gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
    "writeoff_ratio", "collection_efficiency", "n_loans",
]


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


@pytest.fixture
def portfolio() -> pd.DataFrame:
    return _loans([
        {"loan_id": "A", "branch_id": "BR002", "outstanding_npr": 100.0, "days_past_due": 0, "due_npr": 10.0, "collected_npr": 12.0},
        {"loan_id": "B", "outstanding_npr": 200.0, "days_past_due": 30, "restructured": 1, "due_npr": 20.0, "collected_npr": 15.0},
        {"loan_id": "C", "outstanding_npr": 300.0, "days_past_due": 31, "due_npr": 30.0, "collected_npr": 24.0},
        {"loan_id": "D", "branch_id": "BR002", "outstanding_npr": 400.0, "days_past_due": 90, "due_npr": 40.0, "collected_npr": 20.0},
        {"loan_id": "E", "outstanding_npr": 500.0, "days_past_due": 91, "restructured": 1, "due_npr": 50.0, "collected_npr": 10.0},
        {"loan_id": "F", "branch_id": "BR002", "outstanding_npr": 600.0, "days_past_due": 180, "due_npr": 60.0, "collected_npr": 0.0},
        {"loan_id": "G", "outstanding_npr": 700.0, "days_past_due": 181, "due_npr": 70.0, "collected_npr": 5.0},
        {"loan_id": "H", "branch_id": "BR003", "written_off": 1, "outstanding_npr": 0.0, "writeoff_npr": 80.0, "due_npr": 8.0, "collected_npr": 4.0},
        {"loan_id": "OLD", "as_of": PREV, "outstanding_npr": 9999.0, "writeoff_npr": 9999.0},
    ])


def test_defaults_match_frozen_contract():
    assert BUCKETS == ["current", "b1_30", "b31_90", "b91_180", "b180p"]
    assert DEFAULT_CONFIG == {
        "npl_dpd_threshold": 90,
        "provision_rates": {"current": 0.01, "b1_30": 0.05, "b31_90": 0.25, "b91_180": 0.50, "b180p": 1.0},
        "alerts": {"par30_level": 0.10, "par30_jump": 0.02, "roll_rate": 0.05, "collection_drop": 0.05},
    }


@pytest.mark.parametrize("dpd, expected", [
    (0, "current"), (1, "b1_30"), (30, "b1_30"), (31, "b31_90"),
    (90, "b31_90"), (91, "b91_180"), (180, "b91_180"), (181, "b180p"), (999, "b180p"),
])
def test_assign_bucket_boundaries(dpd, expected):
    source = pd.Series([dpd], index=["loan"], name="dpd")
    result = assign_bucket(source)
    assert result.loc["loan"] == expected
    assert result.name == "dpd"
    pd.testing.assert_series_equal(source, pd.Series([dpd], index=["loan"], name="dpd"))


def test_assign_bucket_empty():
    assert assign_bucket(pd.Series(dtype=int)).empty


def test_portfolio_hand_calculated(portfolio):
    result = portfolio_metrics(portfolio, AS_OF)
    assert list(result.columns) == METRICS
    assert len(result) == 1
    # Gross 2800; >30 = 2500; >90 = 1800; restructured = 700.
    assert result.iloc[0].to_dict() == pytest.approx({
        "gross_npr": 2800, "par30": 25 / 28, "par90": 18 / 28, "npl_ratio": 18 / 28,
        "restructured_ratio": 1 / 4, "writeoff_ratio": 80 / 2880,
        "collection_efficiency": 90 / 288, "n_loans": 7,
    }, abs=1e-12)
    assert pd.api.types.is_integer_dtype(result["n_loans"])


def test_grouped_portfolio_includes_written_off_only_branch(portfolio):
    result = portfolio_metrics(portfolio, AS_OF, by=["branch_id"])
    assert list(result.columns) == ["branch_id", *METRICS]
    assert result["branch_id"].tolist() == ["BR001", "BR002", "BR003"]
    assert result.iloc[0][METRICS].to_dict() == pytest.approx({
        "gross_npr": 1700, "par30": 1500 / 1700, "par90": 1200 / 1700,
        "npl_ratio": 1200 / 1700, "restructured_ratio": 700 / 1700,
        "writeoff_ratio": 0, "collection_efficiency": 54 / 170, "n_loans": 4,
    })
    assert result.iloc[1][METRICS].to_dict() == pytest.approx({
        "gross_npr": 1100, "par30": 1000 / 1100, "par90": 600 / 1100,
        "npl_ratio": 600 / 1100, "restructured_ratio": 0,
        "writeoff_ratio": 0, "collection_efficiency": 32 / 110, "n_loans": 3,
    })
    written_off = result.iloc[2]
    assert written_off["gross_npr"] == written_off["n_loans"] == 0
    assert written_off["writeoff_ratio"] == 1.0
    assert written_off["collection_efficiency"] == 0.5
    assert written_off[["par30", "par90", "npl_ratio", "restructured_ratio"]].isna().all()


@pytest.mark.parametrize("threshold, numerator", [(0, 2700), (30, 2500), (90, 1800), (180, 700), (181, 0)])
def test_npl_config_uses_strict_threshold(portfolio, threshold, numerator):
    result = portfolio_metrics(portfolio, AS_OF, config={"npl_dpd_threshold": threshold}).iloc[0]
    assert result["npl_ratio"] == pytest.approx(numerator / 2800)
    assert result["par30"] == pytest.approx(2500 / 2800)
    assert result["par90"] == pytest.approx(1800 / 2800)


def test_bucket_balances_hand_calculated(portfolio):
    result = bucket_balances(portfolio, AS_OF)
    assert list(result.columns) == BUCKETS
    assert result.iloc[0].tolist() == [100, 200, 700, 1100, 700]
    grouped = bucket_balances(portfolio, AS_OF, by=("branch_id",))
    assert grouped.to_dict("records") == [
        {"branch_id": "BR001", "current": 0, "b1_30": 200, "b31_90": 300, "b91_180": 500, "b180p": 700},
        {"branch_id": "BR002", "current": 100, "b1_30": 0, "b31_90": 400, "b91_180": 600, "b180p": 0},
    ]


@pytest.mark.parametrize("function", [portfolio_metrics, bucket_balances])
def test_multiple_group_columns_are_sorted(function):
    loans = _loans([
        {"loan_id": "A", "sector": "Z", "province": "Z", "outstanding_npr": 10},
        {"loan_id": "B", "sector": "A", "province": "Z", "outstanding_npr": 20},
        {"loan_id": "C", "sector": "A", "province": "A", "outstanding_npr": 30},
    ])
    result = function(loans, AS_OF, by=("sector", "province"))
    assert result[["sector", "province"]].values.tolist() == [["A", "A"], ["A", "Z"], ["Z", "Z"]]
    assert result["gross_npr" if function is portfolio_metrics else "current"].tolist() == [30, 20, 10]


@pytest.mark.parametrize("missing_date", [False, True])
def test_empty_portfolio_and_empty_branch(portfolio, missing_date):
    loans = portfolio if missing_date else portfolio.loc[portfolio["branch_id"] == "MISSING"]
    date = "1900-01-31" if missing_date else AS_OF
    result = portfolio_metrics(loans, date)
    assert result.shape == (1, 8)
    assert result.iloc[0]["gross_npr"] == result.iloc[0]["n_loans"] == 0
    assert result.iloc[0][METRICS[1:-1]].isna().all()
    assert bucket_balances(loans, date).iloc[0].tolist() == [0, 0, 0, 0, 0]
    for function, columns in ((portfolio_metrics, METRICS), (bucket_balances, BUCKETS)):
        grouped = function(loans, date, by=("branch_id",))
        assert grouped.empty
        assert list(grouped.columns) == ["branch_id", *columns]


def test_empty_schema_frame():
    result = portfolio_metrics(_loans([]), AS_OF)
    assert result.iloc[0]["gross_npr"] == result.iloc[0]["n_loans"] == 0
    assert result.iloc[0][METRICS[1:-1]].isna().all()
    assert bucket_balances(_loans([]), AS_OF).iloc[0].tolist() == [0] * 5


def test_zero_outstanding_keeps_live_count_and_collections():
    loans = _loans([{"outstanding_npr": 0.0, "due_npr": 20.0, "collected_npr": 30.0}])
    result = portfolio_metrics(loans, AS_OF).iloc[0]
    assert result["gross_npr"] == 0
    assert result["n_loans"] == 1
    assert result[["par30", "par90", "npl_ratio", "restructured_ratio", "writeoff_ratio"]].isna().all()
    assert result["collection_efficiency"] == 1.5  # Do not cap collections at 100%.


def test_zero_due_returns_nan_even_with_positive_collection():
    result = portfolio_metrics(_loans([{"due_npr": 0, "collected_npr": 10}]), AS_OF).iloc[0]
    assert pd.isna(result["collection_efficiency"])


def test_all_current():
    loans = _loans([{"loan_id": str(i), "outstanding_npr": value} for i, value in enumerate([100, 200, 0])])
    result = portfolio_metrics(loans, AS_OF).iloc[0]
    assert result.to_dict() == {
        "gross_npr": 300, "par30": 0, "par90": 0, "npl_ratio": 0,
        "restructured_ratio": 0, "writeoff_ratio": 0, "collection_efficiency": 1, "n_loans": 3,
    }
    assert bucket_balances(loans, AS_OF).iloc[0].tolist() == [300, 0, 0, 0, 0]


def test_writeoff_flow_counts_all_rows_not_only_written_off_flags():
    result = portfolio_metrics(_loans([{"outstanding_npr": 100, "writeoff_npr": 25}]), AS_OF).iloc[0]
    assert result["writeoff_ratio"] == 0.2


def test_portfolio_does_not_mutate_inputs(portfolio):
    before = portfolio.copy(deep=True)
    config = deepcopy(DEFAULT_CONFIG)
    original_config = deepcopy(config)
    first = portfolio_metrics(portfolio, AS_OF, config=config)
    portfolio_metrics(portfolio, AS_OF, by=("branch_id",), config=config)
    bucket_balances(portfolio, AS_OF)
    bucket_balances(portfolio, AS_OF, by=("sector", "province"))
    pd.testing.assert_frame_equal(portfolio, before)
    pd.testing.assert_frame_equal(first, portfolio_metrics(portfolio, AS_OF, config=config))
    assert config == original_config == DEFAULT_CONFIG
