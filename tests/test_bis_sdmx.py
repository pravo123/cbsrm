"""Tests for cbsrm.data.bis_sdmx + cbsrm.indicators.bis_*."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from cbsrm.data import BISStatsClient
from cbsrm.indicators import (
    BISCBSClaimsIndicator,
    BISOTCDerivativesIndicator,
)
from cbsrm.indicators.base import IIndicator


_SAMPLE_OTC_CSV = (
    "FREQ,RISK_CATEGORY,TIME_PERIOD,OBS_VALUE\n"
    "H,O,2024-06-30,632000\n"
    "H,O,2024-12-31,640000\n"
    "H,O,2025-06-30,655000\n"
)


_SAMPLE_CBS_CSV = (
    "FREQ,REPORTING_COUNTRY,TIME_PERIOD,OBS_VALUE\n"
    "Q,5J,2024-03-31,16400\n"
    "Q,5J,2024-06-30,16800\n"
    "Q,5J,2024-09-30,17050\n"
    "Q,5J,2024-12-31,17200\n"
)


def _stub_session(payload: str, *, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = payload
    response.raise_for_status = MagicMock(
        side_effect=(
            requests.HTTPError(f"HTTP {status}") if status >= 400 else None
        )
    )
    sess = MagicMock(spec=requests.Session)
    sess.get.return_value = response
    sess.headers = {}
    return sess


# ─── Client shape ─────────────────────────────────────────────────


def test_client_inits_with_defaults(tmp_path: Path):
    c = BISStatsClient(cache_dir=tmp_path)
    assert c.base_url is not None and "bis.org" in c.base_url


def test_client_session_headers_set_ua(tmp_path: Path):
    sess = MagicMock(spec=requests.Session)
    sess.headers = {}
    BISStatsClient(cache_dir=tmp_path, session=sess)
    assert "User-Agent" in sess.headers
    assert "cbsrm" in sess.headers["User-Agent"]


# ─── get_dataset ──────────────────────────────────────────────────


def test_get_dataset_returns_parsed_dataframe(tmp_path: Path):
    sess = _stub_session(_SAMPLE_OTC_CSV)
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    df = c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")
    assert isinstance(df, pd.DataFrame)
    assert "OBS_VALUE" in df.columns
    assert len(df) == 3


def test_get_dataset_empty_response_returns_empty_df(tmp_path: Path):
    sess = _stub_session("")
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    df = c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")
    assert df.empty


def test_get_dataset_passes_start_period_param(tmp_path: Path):
    sess = _stub_session(_SAMPLE_OTC_CSV)
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    c.get_dataset(flow_id="WS_OTC_DERIV2", key="all",
                  params={"startPeriod": "2010"})
    _, kwargs = sess.get.call_args
    assert kwargs["params"]["startPeriod"] == "2010"
    assert kwargs["params"]["format"] == "csv"


def test_get_dataset_uses_cache_on_second_call(tmp_path: Path):
    sess = _stub_session(_SAMPLE_OTC_CSV)
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    df1 = c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")
    df2 = c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")
    assert sess.get.call_count == 1
    pd.testing.assert_frame_equal(df1, df2)


# ─── Convenience methods ──────────────────────────────────────────


def test_get_otc_derivatives_calls_correct_flow(tmp_path: Path):
    sess = _stub_session(_SAMPLE_OTC_CSV)
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    c.get_otc_derivatives_notional()
    url = sess.get.call_args.args[0]
    assert "WS_OTC_DERIV2" in url


def test_get_consolidated_banking_calls_correct_flow(tmp_path: Path):
    sess = _stub_session(_SAMPLE_CBS_CSV)
    c = BISStatsClient(cache_dir=tmp_path, session=sess)
    c.get_consolidated_banking_claims()
    url = sess.get.call_args.args[0]
    assert "WS_CBS_PUB" in url


# ─── Retry on transient ────────────────────────────────────────────


def test_get_csv_retries_on_500_then_succeeds(tmp_path: Path):
    sess = MagicMock(spec=requests.Session)
    sess.headers = {}
    fail = MagicMock()
    fail.status_code = 500
    fail.text = ""
    fail.raise_for_status = MagicMock(side_effect=requests.HTTPError("500"))
    ok = MagicMock()
    ok.status_code = 200
    ok.text = _SAMPLE_OTC_CSV
    ok.raise_for_status = MagicMock()
    sess.get.side_effect = [fail, ok]
    c = BISStatsClient(cache_dir=tmp_path, session=sess, retry_max=2)
    df = c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")
    assert sess.get.call_count == 2
    assert not df.empty


def test_get_csv_raises_after_exhausting_retries(tmp_path: Path):
    sess = _stub_session("", status=503)
    c = BISStatsClient(cache_dir=tmp_path, session=sess, retry_max=2)
    with pytest.raises(RuntimeError, match="BIS CSV fetch failed"):
        c.get_dataset(flow_id="WS_OTC_DERIV2", key="all")


# ─── Indicators ────────────────────────────────────────────────────


def test_otc_implements_protocol():
    assert isinstance(BISOTCDerivativesIndicator(), IIndicator)
    assert BISOTCDerivativesIndicator().required_series() == ["BIS:WS_OTC_DERIV2"]


def test_cbs_implements_protocol():
    assert isinstance(BISCBSClaimsIndicator(), IIndicator)
    assert BISCBSClaimsIndicator().required_series() == ["BIS:WS_CBS_PUB"]


def test_otc_compute_passes_dataframe_through():
    df = pd.read_csv(io.StringIO(_SAMPLE_OTC_CSV))
    res = BISOTCDerivativesIndicator().compute(df)
    assert res.indicator_id == "BIS-OTC-DERIVATIVES-NOTIONAL"
    assert len(res.values) == 3
    assert res.metadata["latest_value"] == pytest.approx(655000)


def test_cbs_compute_passes_dataframe_through():
    df = pd.read_csv(io.StringIO(_SAMPLE_CBS_CSV))
    res = BISCBSClaimsIndicator().compute(df)
    assert res.indicator_id == "BIS-CBS-CROSS-BORDER-CLAIMS"
    assert len(res.values) == 4
    assert res.metadata["latest_value"] == pytest.approx(17200)


def test_otc_compute_handles_empty_df():
    res = BISOTCDerivativesIndicator().compute(pd.DataFrame())
    assert res.values.empty
    assert res.metadata["n_obs"] == 0


def test_otc_compute_raises_on_missing_columns():
    bad = pd.DataFrame({"FOO": [1, 2, 3]})
    with pytest.raises(ValueError, match="OBS_VALUE"):
        BISOTCDerivativesIndicator().compute(bad)


def test_otc_compute_resolves_lowercase_columns():
    df = pd.DataFrame({
        "time_period": ["2024-03-31", "2024-06-30"],
        "obs_value": [100.0, 110.0],
    })
    res = BISOTCDerivativesIndicator().compute(df)
    assert len(res.values) == 2


def test_otc_compute_metadata_includes_interpretation():
    df = pd.read_csv(io.StringIO(_SAMPLE_OTC_CSV))
    res = BISOTCDerivativesIndicator().compute(df)
    assert "interpretation" in res.metadata
    assert "OTC" in res.metadata["interpretation"]


def test_cbs_compute_metadata_includes_interpretation():
    df = pd.read_csv(io.StringIO(_SAMPLE_CBS_CSV))
    res = BISCBSClaimsIndicator().compute(df)
    assert "BIS" in res.metadata["source"]
    assert "cross-border" in res.metadata["interpretation"].lower()
