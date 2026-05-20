"""Tests for cbsrm.indicators.ciss_us_canonical.CISSUSCanonical end-to-end."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.builders import CISSUSBuilder
from cbsrm.builders.ciss_us_builder import CANONICAL_SPECS
from cbsrm.indicators import CISSUSCanonical, SUBINDEX_NAMES
from cbsrm.indicators.ciss_us_canonical import CANONICAL_INPUTS_BY_SUBINDEX


# ─── Static checks ────────────────────────────────────────────────────


def test_canonical_inputs_match_builder_specs():
    """The subindex → columns mapping must match the builder's output columns."""
    expected: dict[str, list[str]] = {n: [] for n in SUBINDEX_NAMES}
    for s in CANONICAL_SPECS:
        expected[s.subindex].append(s.name)
    for name in SUBINDEX_NAMES:
        assert sorted(expected[name]) == sorted(CANONICAL_INPUTS_BY_SUBINDEX[name])


def test_canonical_subindex_count_matches():
    assert set(CANONICAL_INPUTS_BY_SUBINDEX.keys()) == set(SUBINDEX_NAMES)
    for cols in CANONICAL_INPUTS_BY_SUBINDEX.values():
        assert len(cols) == 3


# ─── Indicator surface ────────────────────────────────────────────────


def test_canonical_indicator_id_and_version():
    c = CISSUSCanonical()
    assert c.id == "CISS-US-Canonical"
    assert c.version == "0.1.0"
    assert "Holló" in c.source


def test_canonical_required_series_returns_canonical_input_names():
    """required_series() returns the 15 column names, not the upstream FRED ids."""
    c = CISSUSCanonical()
    req = c.required_series()
    assert len(req) == 15
    expected = [s.name for s in CANONICAL_SPECS]
    assert sorted(req) == sorted(expected)


def test_canonical_rejects_bad_weights():
    with pytest.raises(ValueError):
        CISSUSCanonical(weights=(0.1, 0.1, 0.1, 0.1, 0.1))


def test_canonical_rejects_bad_lambda():
    with pytest.raises(ValueError):
        CISSUSCanonical(ewma_lambda=1.5)


# ─── End-to-end with fake FRED ────────────────────────────────────────


class FakeFRED:
    def __init__(self, n: int = 500, seed: int = 11) -> None:
        self.n = n
        self.seed = seed

    def get_multi(self, ids, **_):
        rng = np.random.default_rng(self.seed)
        idx = pd.date_range("2018-01-01", periods=self.n, freq="W", tz="UTC")
        cols = {}
        for sid in ids:
            base = rng.normal(0.0, 1.0, self.n).cumsum()
            if sid in ("SP500", "DGS10", "DTWEXBGS", "DEXUSEU", "DEXJPUS"):
                cols[sid] = 100.0 + base
            else:
                cols[sid] = base
        return pd.DataFrame(cols, index=idx)


def test_canonical_compute_e2e_with_builder():
    builder = CISSUSBuilder(FakeFRED())
    df, manifest = builder.build()
    assert not df.empty

    indicator = CISSUSCanonical()
    result = indicator.compute(df)

    assert result.indicator_id == "CISS-US-Canonical"
    assert result.values.size > 0
    assert (result.values >= 0).all()
    assert (result.values <= 1).all()
    assert result.subindex_values is not None
    assert set(result.subindex_values.columns) == set(SUBINDEX_NAMES)


def test_canonical_compute_metadata_includes_input_mapping():
    builder = CISSUSBuilder(FakeFRED())
    df, _ = builder.build()
    result = CISSUSCanonical().compute(df)
    mapping = result.metadata["input_mapping"]
    for name, cols in mapping.items():
        assert sorted(cols) == sorted(CANONICAL_INPUTS_BY_SUBINDEX[name])
