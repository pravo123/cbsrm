"""Parity: site/laghubitta_demo.json (generator) vs cbsrm.mfi (library).

Contract: docs/laghubitta_contract.md section 7. The generator
(tools/build_laghubitta_demo.py) does not import cbsrm.mfi, so agreement here
is an independent check of both implementations against the frozen contract.
Tolerance: absolute 1e-9. NaN in Python corresponds to null in JSON.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pandas as pd
import pytest

mfi = pytest.importorskip("cbsrm.mfi")

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "site" / "laghubitta_loans.csv"
JSON = ROOT / "site" / "laghubitta_demo.json"
TOL = 1e-9
METRICS = ["gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
           "writeoff_ratio", "collection_efficiency", "n_loans"]
SCENARIO_IDS = ["base", "rate_up_200bp", "agri_income_shock", "monsoon_seasonal",
                "regional_disaster", "funding_squeeze"]


@pytest.fixture(scope="module")
def loans() -> pd.DataFrame:
    return pd.read_csv(CSV, dtype={"as_of": str, "loan_id": str, "branch_id": str})


@pytest.fixture(scope="module")
def demo() -> dict:
    return json.loads(JSON.read_text(encoding="utf-8"))


def close(expected, actual) -> bool:
    """JSON value (None means NaN) vs library value, absolute tolerance."""
    if expected is None:
        return actual is None or (isinstance(actual, float) and math.isnan(actual))
    if actual is None or (isinstance(actual, float) and math.isnan(actual)):
        return False
    return abs(float(expected) - float(actual)) <= TOL


def assert_metrics(expected: dict, actual: dict, where: str) -> None:
    bad = [k for k in METRICS if not close(expected[k], actual[k])]
    assert not bad, f"{where}: mismatch in {[(k, expected[k], actual[k]) for k in bad]}"


def test_input_hash_matches_csv(demo):
    assert demo["audit"]["input_sha256"] == hashlib.sha256(CSV.read_bytes()).hexdigest()


def test_config_matches_library(demo):
    assert demo["config"] == mfi.DEFAULT_CONFIG


def test_institution(loans, demo):
    assert len(demo["institution"]) == 24
    for row in demo["institution"]:
        lib = mfi.portfolio_metrics(loans, row["as_of"]).iloc[0].to_dict()
        assert_metrics(row, lib, f"institution {row['as_of']}")


def test_branches(loans, demo):
    for as_of in demo["as_of_dates"]:
        lib = mfi.portfolio_metrics(loans, as_of, by=("branch_id",)).set_index("branch_id")
        for br in demo["branches"]:
            row = next(s for s in br["series"] if s["as_of"] == as_of)
            assert br["branch_id"] in lib.index, f"{br['branch_id']} missing at {as_of}"
            assert_metrics(row, lib.loc[br["branch_id"]].to_dict(),
                           f"branch {br['branch_id']} {as_of}")


@pytest.mark.parametrize("col", ["district", "product", "sector"])
def test_breakdowns(loans, demo, col):
    latest = demo["as_of_dates"][-1]
    lib = mfi.portfolio_metrics(loans, latest, by=(col,)).set_index(col)
    rows = demo[f"by_{col}"]
    assert sorted(r["key"] for r in rows) == sorted(lib.index)
    for r in rows:
        assert_metrics(r, lib.loc[r["key"]].to_dict(), f"by_{col} {r['key']}")


def test_segments(loans, demo):
    latest = demo["as_of_dates"][-1]
    lib = mfi.bucket_balances(loans, latest, by=("sector", "province"))
    lib = lib.set_index(["sector", "province"])
    assert len(lib) == len(demo["segments"])
    for seg in demo["segments"]:
        got = lib.loc[(seg["sector"], seg["province"])]
        for b in mfi.BUCKETS:
            assert close(seg[b], got[b]), (seg["sector"], seg["province"], b)


def test_migration(loans, demo):
    m = demo["migration"]
    assert m["states"] == mfi.STATES
    lib = mfi.migration_matrix(loans, m["from_as_of"], m["to_as_of"])
    for fb in mfi.BUCKETS:
        for st in mfi.STATES:
            assert close(m["matrix"][fb][st], lib.loc[fb, st]), (fb, st)
    rr = mfi.roll_rates(lib)
    for fb in mfi.BUCKETS:
        assert close(m["roll_rates"][fb], rr[fb]), fb


def test_concentration(loans, demo):
    latest = demo["as_of_dates"][-1]
    for by, exp in demo["concentration"].items():
        assert close(exp["hhi"], mfi.hhi(loans, latest, by)), by
        assert close(exp["top5_share"], mfi.top_n_share(loans, latest, by, 5)), by


def test_alerts(loans, demo):
    m = demo["migration"]
    lib = mfi.branch_alerts(loans, m["to_as_of"], m["from_as_of"])
    exp = demo["alerts"]
    assert len(exp) >= 5
    assert list(lib["branch_id"]) == [a["branch_id"] for a in exp]
    assert list(lib["rule"]) == [a["rule"] for a in exp]
    assert list(lib["severity"]) == [a["severity"] for a in exp]
    for a, (_, r) in zip(exp, lib.iterrows(), strict=True):
        assert close(a["value"], r["value"]) and close(a["threshold"], r["threshold"]), a


def _generator():
    spec = importlib.util.spec_from_file_location(
        "build_laghubitta_demo", ROOT / "tools" / "build_laghubitta_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_apply_scenario(demo, scenario_id):
    scenarios = {s["id"]: s for s in demo["scenarios"]}
    assert set(scenarios) == set(SCENARIO_IDS)
    sc = scenarios[scenario_id]
    gen = _generator().apply_scenario(demo["segments"], demo["balance_sheet"], sc,
                                      demo["config"])
    lib = mfi.apply_scenario(pd.DataFrame(demo["segments"]), demo["balance_sheet"], sc,
                             demo["config"])
    assert lib["scenario_id"] == gen["scenario_id"] == scenario_id
    for k in ["gross_npr", "par30", "par90", "provisions_npr", "delta_provisions_npr",
              "nii_hit_npr", "capital_npr", "car", "liquidity_gap_90d_npr"]:
        assert close(gen[k], lib[k]), (scenario_id, k, gen[k], lib[k])
    for b in mfi.BUCKETS:
        assert close(gen["buckets"][b], lib["buckets"][b]), (scenario_id, b)
    if scenario_id == "base":
        assert close(lib["delta_provisions_npr"], 0.0)
        assert close(lib["capital_npr"], demo["balance_sheet"]["capital_npr"])


def test_audit_chain_links(demo):
    chain = demo["audit"]["chain"]
    names = [r["name"] for r in chain]
    assert names[:5] == ["institution", "branches", "migration", "concentration", "alerts"]
    assert names[5:] == [f"scenario:{s}" for s in SCENARIO_IDS]
    prev = None
    for r in chain:
        assert r["prev_hash"] == prev
        assert r["input_sha256"] == demo["audit"]["input_sha256"]
        rebuilt = mfi.record(r["name"], r["input_sha256"], {}, {}, prev)
        # Recompute the link hash from the stored component digests (5.2).
        link = hashlib.sha256(json.dumps(
            [prev or "", r["name"], r["input_sha256"], r["params_sha256"], r["output_sha256"]],
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert r["hash"] == link
        assert set(rebuilt) == set(r)
        prev = r["hash"]
    assert demo["audit"]["head_hash"] == prev


def test_audit_output_hashes_match_library(demo):
    """Each block's output digest equals the library record over the JSON block."""
    chain = {r["name"]: r for r in demo["audit"]["chain"]}
    blocks = {"institution": demo["institution"], "branches": demo["branches"],
              "migration": demo["migration"], "concentration": demo["concentration"],
              "alerts": demo["alerts"]}
    for name, block in blocks.items():
        rec = mfi.record(name, demo["audit"]["input_sha256"], {}, block)
        assert rec["output_sha256"] == chain[name]["output_sha256"], name
