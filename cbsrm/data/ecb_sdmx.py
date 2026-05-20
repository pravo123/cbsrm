"""
ECB Data Portal (SDMX) data client.
====================================

Wraps the ECB Statistical Data Warehouse SDMX 2.1 REST API. Uses the
CSV-format query parameter to avoid an SDMX XML dependency:

  GET https://data-api.ecb.europa.eu/service/data/{flowref}/{key}?format=csvdata

ECB data is published under the ECB Open Data Policy — commercial use
permitted with attribution. Each adapter's source_info() surfaces the
attribution string automatically.

USAGE
-----

    from cbsrm.data import ECBSDMXClient
    client = ECBSDMXClient()

    # Composite Indicator of Systemic Stress, euro area, daily
    ciss = client.get_ciss_euro_area()

    # Generic key fetch
    ts = client.get_series(
        flowref="CISS",
        key="D.U2.Z0Z.4F.EC.SS_CIN.IDX",
    )

ENDPOINT
--------

The ECB v3 Data Portal URL is:
  https://data-api.ecb.europa.eu/service/data/{flowref}/{key}?format=csvdata

The legacy SDW URL is:
  https://sdw-wsrest.ecb.europa.eu/service/data/...

This client uses the v3 endpoint. Override via env ECB_SDMX_BASE_URL
if ECB renames or splits the endpoint again.
"""
from __future__ import annotations

import io
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import requests

log = logging.getLogger("cbsrm.data.ecb_sdmx")


DEFAULT_ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
DEFAULT_USER_AGENT = "cbsrm/0.2 (+https://github.com/pravo123/cbsrm)"
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_RETRY_MAX = 3
DEFAULT_RETRY_BACKOFF_S = 1.5


# Canonical CISS series keys
ECB_CISS_EURO_AREA = "D.U2.Z0Z.4F.EC.SS_CIN.IDX"
ECB_CISS_US        = "D.US.Z0Z.4F.EC.SS_CIN.IDX"      # ECB also publishes a US CISS
ECB_CISS_UK        = "D.GB.Z0Z.4F.EC.SS_CIN.IDX"
ECB_CISS_FLOWREF   = "CISS"


@dataclass
class ECBSDMXMeta:
    """Metadata about an ECB SDMX flow."""
    flowref: str
    key: str
    title: str = ""
    units: str = ""
    frequency: str = ""
    source: str = (
        "European Central Bank Statistical Data Warehouse. "
        "Data made available under the ECB Open Data Policy "
        "(commercial use permitted with attribution to ECB)."
    )


@dataclass
class ECBSDMXClient:
    """ECB Data Portal client (CSV-mode, no SDMX XML deps)."""
    base_url: str | None = None
    cache_dir: Path | None = field(default_factory=lambda: Path(".cbsrm_cache/ecb"))
    session: requests.Session | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    retry_max: int = DEFAULT_RETRY_MAX
    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if self.base_url is None:
            self.base_url = os.environ.get("ECB_SDMX_BASE_URL", DEFAULT_ECB_BASE)
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/csv",
        })
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ─── Public API ───────────────────────────────────────────────────

    def source_info(self, flowref: str, key: str) -> ECBSDMXMeta:
        return ECBSDMXMeta(flowref=flowref, key=key)

    def get_series(
        self, flowref: str, key: str,
        start_period: str | None = None,
        end_period: str | None = None,
    ) -> pd.Series:
        """Fetch one ECB SDMX series. Returns a pandas Series with UTC index."""
        url = f"{self.base_url}/{flowref}/{key}"
        params: dict[str, str] = {"format": "csvdata"}
        if start_period:
            params["startPeriod"] = start_period
        if end_period:
            params["endPeriod"] = end_period
        cache_key = self._cache_key(flowref, key, params)
        raw = self._fetch_csv(url, params=params, cache_key=cache_key)
        return self._parse_sdmx_csv(raw, series_name=key)

    def get_ciss_euro_area(
        self, start_period: str | None = None,
        end_period: str | None = None,
    ) -> pd.Series:
        """Convenience: ECB CISS for the euro area."""
        return self.get_series(
            ECB_CISS_FLOWREF, ECB_CISS_EURO_AREA,
            start_period=start_period, end_period=end_period,
        )

    def get_ciss_us(
        self, start_period: str | None = None,
        end_period: str | None = None,
    ) -> pd.Series:
        """Convenience: ECB-published US CISS (independent of CBSRM's own CISS-US)."""
        return self.get_series(
            ECB_CISS_FLOWREF, ECB_CISS_US,
            start_period=start_period, end_period=end_period,
        )

    def get_ciss_uk(
        self, start_period: str | None = None,
        end_period: str | None = None,
    ) -> pd.Series:
        return self.get_series(
            ECB_CISS_FLOWREF, ECB_CISS_UK,
            start_period=start_period, end_period=end_period,
        )

    # ─── HTTP + cache ─────────────────────────────────────────────────

    def _fetch_csv(self, url: str, params: dict, cache_key: str) -> str:
        cached = self._cache_load(cache_key)
        if cached is not None:
            return cached

        last_exc: Exception | None = None
        for attempt in range(self.retry_max):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout_s)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise requests.HTTPError(f"transient ECB {r.status_code}")
                r.raise_for_status()
                self._cache_save(cache_key, r.text)
                return r.text
            except Exception as e:
                last_exc = e
                if attempt + 1 < self.retry_max:
                    sleep = DEFAULT_RETRY_BACKOFF_S * (2 ** attempt)
                    log.info(f"ECB retry {attempt+1}/{self.retry_max} after {sleep}s: {e}")
                    time.sleep(sleep)
        raise RuntimeError(f"ECB fetch failed after {self.retry_max} attempts: {last_exc}")

    # ─── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_sdmx_csv(raw: str, series_name: str) -> pd.Series:
        """Parse SDMX CSV ('csvdata' format).

        The CSV has many dimension columns plus TIME_PERIOD and OBS_VALUE.
        We extract just those two and return a tidy Series.
        """
        if not raw or not raw.strip():
            return pd.Series(dtype=float, name=series_name)
        df = pd.read_csv(io.StringIO(raw))
        # Find time and value columns
        time_col = None
        for cand in ("TIME_PERIOD", "TIME", "OBS_PERIOD", "Time Period"):
            if cand in df.columns:
                time_col = cand
                break
        val_col = None
        for cand in ("OBS_VALUE", "VALUE", "Obs Value"):
            if cand in df.columns:
                val_col = cand
                break
        if time_col is None or val_col is None:
            log.warning(
                f"ECB CSV missing TIME_PERIOD/OBS_VALUE columns; "
                f"got {list(df.columns)}"
            )
            return pd.Series(dtype=float, name=series_name)

        df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[time_col])
        df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
        df = df.dropna(subset=[val_col])
        df = df.sort_values(time_col)
        # Pass the tz-aware Series directly to DatetimeIndex so the UTC tz is
        # preserved; df[time_col].values would coerce to tz-naive numpy datetime64.
        idx = pd.DatetimeIndex(df[time_col], name="date")
        return pd.Series(
            df[val_col].values, index=idx,
            name=series_name, dtype=float,
        )

    # ─── Cache helpers ────────────────────────────────────────────────

    @staticmethod
    def _cache_key(flowref: str, key: str, params: dict) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in f"{flowref}_{key}")
        if "startPeriod" in params or "endPeriod" in params:
            safe += f"_{params.get('startPeriod','-')}_{params.get('endPeriod','-')}"
        return f"{safe}.csv"

    def _cache_load(self, key: str) -> str | None:
        if self.cache_dir is None:
            return None
        p = self.cache_dir / key
        if not p.exists():
            return None
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None

    def _cache_save(self, key: str, body: str) -> None:
        if self.cache_dir is None:
            return
        try:
            (self.cache_dir / key).write_text(body, encoding="utf-8")
        except OSError as e:
            log.warning(f"ECB cache write failed: {e}")
