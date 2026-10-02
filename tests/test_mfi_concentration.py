"""Hand-calculated concentration shares for live loans only."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from cbsrm.mfi import hhi, top_n_share
from tests.test_mfi_portfolio import AS_OF, PREV, _loans


@pytest.mark.parametrize("by", ["district", "sector", "product", "branch_id"])
def test_concentration_aggregates_groups_before_squaring(by):
    loans = _loans([
        {"loan_id": str(i), by: group, "outstanding_npr": balance}
        for i, (group, balance) in enumerate([("A", 30), ("A", 30), ("B", 25), ("C", 10), ("D", 5)])
    ] + [
        {"loan_id": "W", by: "W", "written_off": 1, "outstanding_npr": 0, "writeoff_npr": 10000},
        {"loan_id": "OLD", "as_of": PREV, by: "OLD", "outstanding_npr": 10000},
    ])
    # Shares .60, .25, .10, .05: HHI .36 + .0625 + .01 + .0025 = .435.
    assert hhi(loans, AS_OF, by) == pytest.approx(0.435)
    assert top_n_share(loans, AS_OF, by, n=1) == pytest.approx(0.6)
    assert top_n_share(loans, AS_OF, by, n=2) == pytest.approx(0.85)
    assert top_n_share(loans, AS_OF, by) == 1.0
    assert top_n_share(loans, AS_OF, by, n=20) == 1.0
    assert top_n_share(loans, AS_OF, by, n=0) == 0.0


def test_default_top_five_out_of_six():
    loans = _loans([{"loan_id": str(i), "sector": str(i), "outstanding_npr": i} for i in range(1, 7)])
    assert top_n_share(loans, AS_OF, "sector") == pytest.approx(20 / 21)
    assert hhi(loans, AS_OF, "sector") == pytest.approx(91 / 441)


def test_single_group_all_current():
    loans = _loans([{"loan_id": "A"}, {"loan_id": "B"}])
    assert hhi(loans, AS_OF, "sector") == 1.0
    assert top_n_share(loans, AS_OF, "sector") == 1.0


@pytest.mark.parametrize("rows", [[], [{"outstanding_npr": 0}], [{"written_off": 1, "outstanding_npr": 0}], [{"as_of": PREV}]])
def test_zero_denominators(rows):
    loans = _loans(rows)
    assert math.isnan(hhi(loans, AS_OF, "sector"))
    assert math.isnan(top_n_share(loans, AS_OF, "sector"))


def test_concentration_does_not_mutate_inputs():
    loans = _loans([{"sector": "A"}, {"loan_id": "B", "sector": "B"}])
    before = loans.copy(deep=True)
    hhi(loans, AS_OF, "sector")
    top_n_share(loans, AS_OF, "sector")
    pd.testing.assert_frame_equal(loans, before)
