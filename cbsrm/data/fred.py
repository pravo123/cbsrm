"""
FRED (St. Louis Fed) data client.
==================================

Wraps the public FRED API with:
  - Typed pydantic models for series metadata
  - Pandas DataFrame outputs with UTC-tz indexes
  - Local file-cache for repeatability (no rate-limit hits on re-run)
  - Source-info accessor for derived-work license attribution

Authentication
--------------

Requires a free FRED API key. Register at https://fredaccount.stlouisfed.org/.
Pass via:
  - constructor `FREDClient(api_key="...")`
  - or env var `FRED_API_KEY`

License (per FRED API ToS, 2026-05)
-----------------------------------

FRED data are sourced upstream from public agencies (Fed Board, BLS,
Treasury, BEA). Each underlying series has its own license terms;
FRED itself is in the public domain. Derived analytics are unrestricted
for commercial use.

For full compliance:
  client = FREDClient(api_key=...)
  meta = client.series_meta("SOFR")
  # meta.notes, meta.units, meta.frequency contain attribution info

Series mnemonics relevant to CBSRM v0.1
---------------------------------------

| Mnemonic         | Series                                              |
|------------------|-----------------------------------------------------|
| SOFR             | Secured Overnight Financing Rate                    |
| IORB             | Interest on Reserve Balances                        |
| EFFR             | Effective Federal Funds Rate                        |
| SWPT             | Central Bank Liquidity Swaps (Wed level)            |
| WALCL            | Fed Balance Sheet — total assets                    |
| RRPONTSYD        | Reverse Repo Facility                               |
| T10Y2Y           | 10Y minus 2Y Treasury spread                        |
| T10Y3M           | 10Y minus 3M Treasury spread                        |
| TEDRATE          | TED spread (3M USD LIBOR − 3M T-Bill)               |
| BAMLH0A0HYM2     | ICE BofA US High-Yield OAS                          |
| BAMLC0A0CM       | ICE BofA US Corporate Index OAS                     |
| VIXCLS           | VIX (close)                                         |
| KCFSI            | Kansas City Fed Financial Stress Index              |
| STLFSI4          | St. Louis Fed Financial Stress Index (v4)           |
| NFCI             | Chicago Fed National Financial Conditions Index     |
| ANFCI            | NFCI Adjusted                                        |
| DTWEXBGS         | Trade-weighted USD index (broad)                    |
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import requests

log = logging.getLogger("cbsrm.data.fred")


FRED_API_BASE = "https://api.stlouisfed.org/fred"
FRED_API_KEY_ENV = "FRED_API_KEY"
DEFAULT_USER_AGENT = "cbsrm/0.1 (+https://github.com/pravo123/cbsrm)"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRY_MAX = 3
DEFAULT_RETRY_BACKOFF_S = 1.0


@dataclass
class FREDSeriesMeta:
    """Metadata for one FRED series."""
    series_id: str
    title: str
    units: str
    frequency: str           # 'D', 'W', 'M', 'Q', 'A', etc.
    seasonal_adjustment: str
    observation_start: str    # ISO date
    observation_end: str      # ISO date
    last_updated: str
    notes: str
    source: str = "FRED (Federal Reserve Bank of St. Louis)"

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> FREDSeriesMeta:
        s = payload["seriess"][0] if "seriess" in payload else payload
        return cls(
            series_id=s.get("id", ""),
            title=s.get("title", ""),
            units=s.get("units", ""),
            frequency=s.get("frequency_short", s.get("frequency", "")),
            seasonal_adjustment=s.get("seasonal_adjustment_short", ""),
            observation_start=s.get("observation_start", ""),
            observation_end=s.get("observation_end", ""),
            last_updated=s.get("last_updated", ""),
            notes=s.get("notes", "") or "",
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "series_id": self.series_id,
            "title": self.title,
            "units": self.units,
            "frequency": self.frequency,
            "seasonal_adjustment": self.seasonal_adjustment,
            "observation_start": self.observation_start,
            "observation_end": self.observation_end,
            "last_updated": self.last_updated,
            "source": self.source,
        }


@dataclass
class FREDClient:
    """Public FRED API client with file-cache + retry.

    Parameters
    ----------
    api_key : str, optional
        FRED API key. If None, reads from env var ``FRED_API_KEY``.
    cache_dir : Path, optional
        Local directory for response cache. Defaults to ``./.cbsrm_cache/fred``.
        Set to None to disable caching.
    session : requests.Session, optional
        Pre-configured session (for testing).
    timeout_s : float
        Per-request timeout. Default 30s.
    retry_max : int
        Max retries on transient errors (429, 5xx, network). Default 3.
    user_agent : str
        Sent on every request. Default cbsrm/0.1.
    """
    api_key: str | None = None
    cache_dir: Path | None = field(default_factory=lambda: Path(".cbsrm_cache/fred"))
    session: requests.Session | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    retry_max: int = DEFAULT_RETRY_MAX
    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get(FRED_API_KEY_ENV)
        if not self.api_key:
            log.warning(
                "No FRED API key provided. Set FRED_API_KEY env or pass api_key=. "
                "Live requests will fail with 400."
            )
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ─── Public API ───────────────────────────────────────────────────

    def series_meta(self, series_id: str) -> FREDSeriesMeta:
        """Return metadata for one series. Cached."""
        payload = self._get(
            "/series",
            params={"series_id": series_id, "file_type": "json"},
            cache_key=f"meta_{series_id}.json",
        )
        return FREDSeriesMeta.from_api(payload)

    def get_series(
        self,
        series_id: str,
        *,
        observation_start: str | None = None,
        observation_end: str | None = None,
        frequency: str | None = None,
        aggregation_method: str = "avg",
        units: str = "lin",
    ) -> pd.Series:
        """Return one series as a pandas Series with UTC-tz DateTimeIndex.

        Parameters mirror FRED API. ``frequency`` accepts 'd','w','bw','m','q','sa','a'.
        Missing values are filtered out.
        """
        params: dict[str, Any] = {
            "series_id": series_id,
            "file_type": "json",
            "aggregation_method": aggregation_method,
            "units": units,
        }
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end
        if frequency:
            params["frequency"] = frequency

        cache_key = self._series_cache_key(series_id, params)
        payload = self._get(
            "/series/observations", params=params, cache_key=cache_key,
        )
        return self._parse_observations(payload, series_id)

    def get_multi(
        self, series_ids: list[str], **kwargs: Any,
    ) -> pd.DataFrame:
        """Convenience: fetch multiple series, return aligned DataFrame.

        Returns wide DataFrame with one column per series_id.
        """
        cols: dict[str, pd.Series] = {}
        for sid in series_ids:
            try:
                cols[sid] = self.get_series(sid, **kwargs)
            except Exception as e:
                log.warning(f"FRED fetch failed for {sid}: {e}")
                cols[sid] = pd.Series(dtype=float, name=sid)
        df = pd.DataFrame(cols)
        df.index.name = "date"
        return df

    # ─── Internals ────────────────────────────────────────────────────

    def _get(self, endpoint: str, *, params: dict[str, Any],
             cache_key: str | None = None) -> dict[str, Any]:
        # Check cache
        if cache_key and self.cache_dir is not None:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached

        params = {**params, "api_key": self.api_key}
        url = FRED_API_BASE + endpoint

        last_exc: Exception | None = None
        for attempt in range(self.retry_max):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout_s)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise requests.HTTPError(f"transient FRED {r.status_code}")
                r.raise_for_status()
                payload = r.json()
                if cache_key and self.cache_dir is not None:
                    self._cache_save(cache_key, payload)
                return payload
            except Exception as e:
                last_exc = e
                if attempt + 1 < self.retry_max:
                    sleep = DEFAULT_RETRY_BACKOFF_S * (2 ** attempt)
                    log.info(f"FRED retry {attempt+1}/{self.retry_max} after {sleep}s: {e}")
                    time.sleep(sleep)
        raise RuntimeError(f"FRED request failed after {self.retry_max} attempts: {last_exc}")

    @staticmethod
    def _series_cache_key(series_id: str, params: dict[str, Any]) -> str:
        clean = {k: v for k, v in params.items() if k != "api_key"}
        suffix = "_".join(f"{k}-{v}" for k, v in sorted(clean.items()) if k != "series_id")
        return f"obs_{series_id}_{suffix}.json"

    def _cache_load(self, key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / key
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning(f"cache read failed for {key}: {e}")
            return None

    def _cache_save(self, key: str, payload: dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / key
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f)
        except OSError as e:
            log.warning(f"cache write failed for {key}: {e}")

    @staticmethod
    def _parse_observations(payload: dict[str, Any], series_id: str) -> pd.Series:
        obs = payload.get("observations", [])
        if not obs:
            return pd.Series(dtype=float, name=series_id)

        dates: list[pd.Timestamp] = []
        values: list[float] = []
        for o in obs:
            v = o.get("value")
            if v in (None, ".", ""):
                continue
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                continue
            dates.append(pd.Timestamp(o["date"], tz="UTC"))
        if not values:
            return pd.Series(dtype=float, name=series_id)
        return pd.Series(values, index=pd.DatetimeIndex(dates, name="date"),
                         name=series_id, dtype=float)
