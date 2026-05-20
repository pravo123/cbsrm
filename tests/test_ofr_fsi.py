"""Tests for cbsrm.indicators.ofr_fsi.OFRFSIWrap."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cbsrm.indicators import OFRFSIWrap
from cbsrm.indicators.base import IIndicator


def _sample_fsi_df(n: int = 20):
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({
        "OFR FSI": np.linspace(-1.0, 3.0, n),
        "Credit": np.linspace(-0.5, 1.0, n),
        "Equity valuation": np.linspace(0.0, 0.8, n),
        "Funding": np.linspace(-0.2, 0.6, n),
        "Safe assets": np.linspace(-0.3, 0.4, n),
        "Volatility": np.linspace(0.0, 0.7, n),
    }, index=idx)


def test_protocol_conformance():
    w = OFRFSIWrap()
    assert isinstance(w, IIndicator)
    assert w.id == "OFR-FSI"
    assert "Office of Financial Research" in w.source


def test_required_series():
    assert OFRFSIWrap().required_series() == ["OFR FSI"]


def test_compute_extracts_composite():
    df = _sample_fsi_df()
    result = OFRFSIWrap().compute(df)
    assert result.indicator_id == "OFR-FSI"
    assert result.values.name == "OFR-FSI"
    assert len(result.values) == 20
    assert result.values.iloc[-1] == pytest.approx(3.0)


def test_compute_extracts_subindex_breakdown():
    df = _sample_fsi_df()
    result = OFRFSIWrap().compute(df)
    assert result.subindex_values is not None
    assert set(result.subindex_values.columns) == {
        "credit", "equity_valuation", "funding", "safe_assets", "volatility",
    }


def test_compute_works_when_only_composite_present():
    """Subindex breakdown is optional; just the composite suffices."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D", tz="UTC")
    df = pd.DataFrame({"OFR FSI": np.arange(10.0)}, index=idx)
    result = OFRFSIWrap().compute(df)
    assert result.subindex_values is None or result.subindex_values.empty
    assert len(result.values) == 10


def test_compute_recognizes_alternate_composite_column():
    idx = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    df = pd.DataFrame({"OFRFSI": [0.1, 0.2, 0.3, 0.4, 0.5]}, index=idx)
    result = OFRFSIWrap().compute(df)
    assert len(result.values) == 5


def test_compute_explicit_override():
    idx = pd.date_range("2020-01-01", periods=4, freq="D", tz="UTC")
    df = pd.DataFrame({"MY_STRESS_COL": [0.1, 0.2, 0.3, 0.4]}, index=idx)
    result = OFRFSIWrap(composite_col="MY_STRESS_COL").compute(df)
    assert result.values.iloc[-1] == pytest.approx(0.4)


def test_compute_raises_when_no_recognizable_column():
    idx = pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")
    df = pd.DataFrame({"random_col": [1, 2, 3]}, index=idx)
    with pytest.raises(ValueError, match="composite column"):
        OFRFSIWrap().compute(df)


def test_compute_drops_nan_in_composite():
    idx = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    df = pd.DataFrame({
        "OFR FSI": [0.1, np.nan, 0.3, np.nan, 0.5],
    }, index=idx)
    result = OFRFSIWrap().compute(df)
    assert len(result.values) == 3


def test_metadata_includes_interpretation():
    df = _sample_fsi_df()
    result = OFRFSIWrap().compute(df)
    assert "interpretation" in result.metadata
    assert "Z-score" in result.metadata["interpretation"]


def test_metadata_records_column_resolution():
    df = _sample_fsi_df()
    result = OFRFSIWrap().compute(df)
    assert result.metadata["composite_column_used"] == "OFR FSI"
    assert "credit" in result.metadata["subindex_columns_used"]
