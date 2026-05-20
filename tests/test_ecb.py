"""Tests for cbsrm.data.ecb_sdmx.ECBSDMXClient + cbsrm.indicators.ecb_ciss."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cbsrm.data.ecb_sdmx import (
    ECB_CISS_EURO_AREA, ECB_CISS_FLOWREF, ECBSDMXClient, ECBSDMXMeta,
)
from cbsrm.indicators import ECBCISSWrap
from cbsrm.indicators.base import IIndicator


# Minimal SDMX csvdata-format sample. Real ECB output has many dimension
# columns; only TIME_PERIOD + OBS_VALUE are needed by our parser.
_CISS_CSV = """\
DATAFLOW,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE
ECB:CISS(1.0),D,U2,2020-02-15,0.10
ECB:CISS(1.0),D,U2,2020-03-15,0.55
ECB:CISS(1.0),D,U2,2020-04-15,0.42
ECB:CISS(1.0),D,U2,2020-05-15,0.21
"""


@pytest.fixture
def fake_session():
    s = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.text = _CISS_CSV
    s.get = MagicMock(return_value=resp)
    return s, resp


@pytest.fixture
def client(tmp_path, fake_session):
    sess, _ = fake_session
    return ECBSDMXClient(cache_dir=tmp_path / "ecb", session=sess)


# ─── Client init ──────────────────────────────────────────────────────


def test_default_base_url(monkeypatch, tmp_path):
    monkeypatch.delenv("ECB_SDMX_BASE_URL", raising=False)
    c = ECBSDMXClient(cache_dir=tmp_path / "ecb")
    assert "data-api.ecb.europa.eu" in c.base_url


def test_env_base_url_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ECB_SDMX_BASE_URL", "https://example.org/v3/data")
    c = ECBSDMXClient(cache_dir=tmp_path / "ecb")
    assert c.base_url == "https://example.org/v3/data"


def test_source_info_returns_metadata(client):
    meta = client.source_info("CISS", "D.U2.Z0Z.4F.EC.SS_CIN.IDX")
    assert isinstance(meta, ECBSDMXMeta)
    assert meta.flowref == "CISS"
    assert "European Central Bank" in meta.source


# ─── get_series ───────────────────────────────────────────────────────


def test_get_ciss_euro_area_returns_series(client):
    s = client.get_ciss_euro_area()
    assert isinstance(s, pd.Series)
    assert len(s) == 4
    assert s.iloc[1] == pytest.approx(0.55)


def test_get_series_uses_correct_endpoint(client, fake_session):
    sess, _ = fake_session
    client.get_series("CISS", "D.U2.Z0Z.4F.EC.SS_CIN.IDX")
    call = sess.get.call_args
    url = call.args[0] if call.args else call.kwargs.get("url")
    assert "CISS" in url
    assert "D.U2.Z0Z.4F.EC.SS_CIN.IDX" in url


def test_get_series_passes_format_csv(client, fake_session):
    sess, _ = fake_session
    client.get_series("CISS", "D.U2.Z0Z.4F.EC.SS_CIN.IDX")
    call = sess.get.call_args
    params = call.kwargs.get("params", {})
    assert params.get("format") == "csvdata"


def test_get_series_with_date_range(client, fake_session):
    sess, _ = fake_session
    client.get_series("CISS", "D.U2.Z0Z.4F.EC.SS_CIN.IDX",
                      start_period="2020-01-01", end_period="2020-12-31")
    call = sess.get.call_args
    params = call.kwargs.get("params", {})
    assert params["startPeriod"] == "2020-01-01"
    assert params["endPeriod"] == "2020-12-31"


def test_get_series_index_is_utc(client):
    s = client.get_ciss_euro_area()
    assert s.index.tz is not None
    assert str(s.index.tz) == "UTC"


def test_get_series_cached_on_second_call(fake_session, tmp_path):
    sess, _ = fake_session
    c = ECBSDMXClient(cache_dir=tmp_path / "ecb", session=sess)
    c.get_ciss_euro_area()
    c.get_ciss_euro_area()
    assert sess.get.call_count == 1


def test_parse_handles_empty_csv():
    parsed = ECBSDMXClient._parse_sdmx_csv("", series_name="X")
    assert parsed.empty
    assert parsed.name == "X"


def test_parse_handles_missing_columns():
    parsed = ECBSDMXClient._parse_sdmx_csv("foo,bar\n1,2\n", series_name="X")
    assert parsed.empty


# ─── ECBCISSWrap indicator ────────────────────────────────────────────


def test_ecb_ciss_wrap_protocol():
    w = ECBCISSWrap()
    assert isinstance(w, IIndicator)
    assert w.id == "ECB-CISS-EA"


def test_ecb_ciss_variant_rejection():
    with pytest.raises(ValueError, match="variant"):
        ECBCISSWrap(variant="ZZ")


def test_ecb_ciss_variant_us():
    w = ECBCISSWrap(variant="US")
    assert w.id == "ECB-CISS-US"
    assert "United States" in w.compute(_dummy_series()).metadata["variant_label"]


def test_ecb_ciss_compute_from_series():
    s = _dummy_series()
    result = ECBCISSWrap().compute(s)
    assert result.indicator_id == "ECB-CISS-EA"
    assert len(result.values) == 4


def test_ecb_ciss_compute_from_dataframe_single_col():
    s = _dummy_series()
    df = s.to_frame(name="anything")
    result = ECBCISSWrap().compute(df)
    assert len(result.values) == 4


def test_ecb_ciss_compute_finds_by_id_column():
    s = _dummy_series()
    df = s.to_frame(name="ECB-CISS-EA")
    df["other"] = 0.0
    result = ECBCISSWrap().compute(df)
    assert result.values.iloc[1] == pytest.approx(0.55)


def test_ecb_ciss_compute_raises_when_unresolvable():
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]},
                      index=pd.date_range("2020-01-01", periods=2, tz="UTC"))
    with pytest.raises(ValueError, match="cannot find"):
        ECBCISSWrap().compute(df)


def _dummy_series():
    idx = pd.DatetimeIndex(
        ["2020-02-15", "2020-03-15", "2020-04-15", "2020-05-15"],
        tz="UTC",
    )
    return pd.Series([0.10, 0.55, 0.42, 0.21], index=idx, name="ECB-CISS-EA")
