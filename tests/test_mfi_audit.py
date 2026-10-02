"""Canonical audit vectors cross-checked independently with .NET SHA256."""
from __future__ import annotations

from copy import deepcopy

import pytest

from cbsrm.mfi import record

INPUT_HASH = "38364585620de063fe9657d50f7cca4b01954854115b0528fe55b8762f3eaa04"
PARAMS_HASH = "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
OUTPUT_HASH = "ee42beb572a1dec2abaa1e7bae3da3238c08cde5d41d9daa376e2f424f9f555b"
HEAD_HASH = "d11da47deb67016c0e6fb270de79be5d6c52451b6a5f92a8aff5d6a4590e264b"
SECOND_HASH = "6207c15d8a266bc7027048bb24c4daf9d0a27bdefa09fe8fa86e38aca50f07f8"


def test_record_exact_canonical_hash_vector():
    # Input bytes: b"synthetic loans\n".
    # Canonical params: {"a":1,"b":2}; output: {"missing":null,"result":0.125}.
    result = record("portfolio", INPUT_HASH, {"b": 2, "a": 1}, {"result": 0.125, "missing": None})
    assert result == {
        "name": "portfolio", "input_sha256": INPUT_HASH, "params_sha256": PARAMS_HASH,
        "output_sha256": OUTPUT_HASH, "prev_hash": None, "hash": HEAD_HASH,
    }


def test_record_links_to_previous_hash():
    result = record("portfolio", INPUT_HASH, {"a": 1, "b": 2}, {"missing": None, "result": 0.125}, HEAD_HASH)
    assert result["prev_hash"] == HEAD_HASH
    assert result["hash"] == SECOND_HASH
    assert result["params_sha256"] == PARAMS_HASH
    assert result["output_sha256"] == OUTPUT_HASH


def test_empty_previous_hash_and_none_have_same_hash_but_preserve_field():
    result = record("portfolio", INPUT_HASH, {"a": 1, "b": 2}, {"missing": None, "result": 0.125}, "")
    assert result["prev_hash"] == ""
    assert result["hash"] == HEAD_HASH


def test_key_order_and_repeated_calls_do_not_change_hashes():
    first = record("portfolio", INPUT_HASH, {"b": 2, "a": 1}, {"result": 0.125, "missing": None})
    second = record("portfolio", INPUT_HASH, {"a": 1, "b": 2}, {"missing": None, "result": 0.125})
    assert first == second
    assert "timestamp" not in first


@pytest.mark.parametrize("field", ["name", "input_sha256", "params", "output", "prev_hash"])
def test_each_hashed_input_changes_record_hash(field):
    args = {"name": "portfolio", "input_sha256": INPUT_HASH, "params": {"a": 1, "b": 2}, "output": {"missing": None, "result": 0.125}, "prev_hash": None}
    args[field] = {"changed": True} if field in {"params", "output"} else "changed"
    assert record(**args)["hash"] != HEAD_HASH


def test_empty_dict_hash_and_no_mutation():
    params = {"scenario": {"sector_mult": {"Agriculture": 2}, "base_shift": 0.2}}
    original = deepcopy(params)
    output = {}
    result = record("stress", INPUT_HASH, params, output)
    assert result["output_sha256"] == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
    assert params == original
    assert output == {}
