"""
BIS Statistical Data Portal client (SDMX 2.1 REST API, CSV mode).

WHAT THIS PROVIDES
------------------

The Bank for International Settlements publishes the most authoritative
cross-jurisdiction financial-stability datasets in existence:

* Consolidated banking statistics (CBS) — cross-border claims on
  immediate counterparty + ultimate risk basis, quarterly, by country
* Locational banking statistics (LBS) — cross-border bank claims by
  residence, quarterly
* OTC derivatives statistics — notional outstanding by risk class
  (interest rate / FX / equity / commodity / credit / other),
  semi-annual, with gross market value + gross credit exposure
* Effective exchange rates (EER) — narrow + broad, daily / monthly
* FX turnover (Triennial Survey) — once every three years
* Domestic credit gap + global liquidity indicators

All publicly free under BIS's open data policy (attribution required).
The endpoint is SDMX 2.1 REST at ``stats.bis.org``.

DESIGN
------

Mirrors ``cbsrm.data.ecb_sdmx.ECBSDMXClient`` — same file-cache, same
retry-on-transient, same session pattern, same convenience methods next to
a generic ``get_dataset()`` for arbitrary BIS flows.

CSV mode is used (no XML SDMX parsing dependency). The endpoint:

    https://stats.bis.org/api/v2/data/dataflow/BIS/{flow_id}/{version}/{key}?format=csv

USAGE
-----

::

    from cbsrm.data import BISStatsClient
    client = BISStatsClient()
    # OTC derivatives — notional outstanding, all currencies, all instruments
    otc = client.get_otc_derivatives_notional()
    # Consolidated banking statistics — cross-border claims, all reporting banks
    cbs = client.get_consolidated_banking_claims()
    # Generic
    df = client.get_dataset(flow_id="WS_OTC_DERIV2", key="H.S.O.A.5J.A.5R.A.A.TO1.TO1")

CITATION
--------

Bank for International Settlements (2026). BIS Statistical Bulletin.
https://stats.bis.org. Used under the BIS Open Data Policy
(non-commercial + commercial use permitted with attribution).
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

log = logging.getLogger("cbsrm.data.bis_sdmx")


DEFAULT_BIS_BASE = "https://stats.bis.org/api/v2"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; cbsrm/0.6 research-bot; "
    "+https://github.com/pravo123/cbsrm)"
)
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_RETRY_MAX = 3
DEFAULT_RETRY_BACKOFF_S = 2.0


# Default BIS dataflow IDs + sample keys. BIS occasionally rotates these;
# operators can override per call via `get_dataset(flow_id, key)`.
BIS_OTC_DERIVATIVES_FLOW = "WS_OTC_DERIV2"
BIS_OTC_DERIVATIVES_DEFAULT_KEY = "H.A.A.A.A.A.A.A.A.5J.A"  # placeholder; configurable

BIS_CBS_FLOW = "WS_CBS_PUB"
BIS_CBS_DEFAULT_KEY = "Q.S.5J.4R.U.X.A.A.TO1.A.5J"           # placeholder; configurable

BIS_LBS_FLOW = "WS_LBS_D_PUB"
BIS_EER_FLOW = "WS_EER"


@dataclass
class BISStatsMeta:
    """Metadata about a BIS Stats dataflow."""
    flow_id: str
    key: str
    title: str = ""
    units: str = ""
    frequency: str = ""
    source: str = (
        "Bank for International Settlements Statistical Bulletin. "
        "https://stats.bis.org. Used under the BIS Open Data Policy "
        "(commercial use permitted with attribution)."
    )


@dataclass
class BISStatsClient:
    """BIS Stats SDMX 2.1 REST client (CSV mode).

    Parameters
    ----------
    base_url : optional override (default ``https://stats.bis.org/api/v2``)
    cache_dir : local file-cache directory (default ``.cbsrm_cache/bis``)
    session : injected ``requests.Session`` for test mocking
    timeout_s : per-request timeout in seconds
    retry_max : maximum retries on 5xx / 429
    user_agent : User-Agent header (BIS occasionally rate-limits bot UAs)
    """
    base_url: str | None = None
    cache_dir: Path | None = field(default_factory=lambda: Path(".cbsrm_cache/bis"))
    session: requests.Session | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    retry_max: int = DEFAULT_RETRY_MAX
    user_agent: str = DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        if self.base_url is None:
            self.base_url = os.environ.get("BIS_STATS_BASE_URL", DEFAULT_BIS_BASE)
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/csv, application/vnd.sdmx.data+csv, */*;q=0.5",
        })
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ─── Public API ─────────────────────────────────────────────────

    def source_info(self, flow_id: str = "", key: str = "") -> BISStatsMeta:
        return BISStatsMeta(flow_id=flow_id, key=key)

    def get_dataset(
        self,
        flow_id: str,
        key: str = "all",
        *,
        version: str = "1.0",
        params: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Fetch a BIS dataflow as a pandas DataFrame.

        Parameters
        ----------
        flow_id : str
            BIS dataflow ID (e.g. ``WS_OTC_DERIV2``, ``WS_CBS_PUB``).
        key : str
            SDMX key. ``"all"`` returns the entire dataset (large).
        version : str
            Dataflow version (default ``"1.0"``).
        params : dict, optional
            Additional URL params (e.g. ``{"startPeriod": "2010"}``).

        Returns
        -------
        pd.DataFrame
            Whatever BIS returns in CSV; the schema is dataflow-specific
            but always includes ``OBS_VALUE`` + a ``TIME_PERIOD`` column.
        """
        path = f"/data/dataflow/BIS/{flow_id}/{version}/{key}"
        req_params: dict[str, Any] = {"format": "csv"}
        if params:
            req_params.update(params)
        cache_key = self._cache_key(flow_id, version, key, req_params)
        text = self._get_csv(path, params=req_params, cache_key=cache_key)
        if not text or not text.strip():
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(text))

    def get_otc_derivatives_notional(
        self,
        *,
        key: str | None = None,
        start_period: str | None = None,
    ) -> pd.DataFrame:
        """Fetch BIS OTC derivatives notional outstanding.

        Default key targets the all-instrument all-currency aggregate. For
        per-risk-class breakdowns (interest rate / FX / equity / commodity
        / credit / other), pass a configured ``key``.
        """
        params = {"startPeriod": start_period} if start_period else None
        return self.get_dataset(
            flow_id=BIS_OTC_DERIVATIVES_FLOW,
            key=key or BIS_OTC_DERIVATIVES_DEFAULT_KEY,
            params=params,
        )

    def get_consolidated_banking_claims(
        self,
        *,
        key: str | None = None,
        start_period: str | None = None,
    ) -> pd.DataFrame:
        """Fetch BIS Consolidated Banking Statistics — cross-border claims.

        Default key targets the global aggregate on immediate-counterparty
        basis. For per-country breakdowns, pass a configured ``key``.
        """
        params = {"startPeriod": start_period} if start_period else None
        return self.get_dataset(
            flow_id=BIS_CBS_FLOW,
            key=key or BIS_CBS_DEFAULT_KEY,
            params=params,
        )

    # ─── Internals ──────────────────────────────────────────────────

    def _get_csv(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> str:
        """GET a CSV resource with cache + retry."""
        if cache_key and self.cache_dir is not None:
            cached = self._cache_load(cache_key)
            if cached is not None:
                return cached

        url = f"{(self.base_url or DEFAULT_BIS_BASE).rstrip('/')}{path}"
        assert self.session is not None
        last_exc: Exception | None = None
        for attempt in range(self.retry_max):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    raise requests.HTTPError(f"transient BIS {resp.status_code}")
                resp.raise_for_status()
                text = resp.text
                if cache_key and self.cache_dir is not None:
                    self._cache_save(cache_key, text)
                return text
            except Exception as e:
                last_exc = e
                if attempt + 1 < self.retry_max:
                    sleep = DEFAULT_RETRY_BACKOFF_S * (2 ** attempt)
                    log.info(f"BIS retry {attempt+1}/{self.retry_max} after {sleep}s: {e}")
                    time.sleep(sleep)
        raise RuntimeError(
            f"BIS CSV fetch failed after {self.retry_max} attempts: {last_exc}"
        )

    @staticmethod
    def _cache_key(flow_id: str, version: str, key: str,
                   params: dict[str, Any]) -> str:
        clean = {k: v for k, v in params.items() if v is not None}
        suffix = "_".join(
            f"{k}-{v}" for k, v in sorted(clean.items()) if k != "format"
        )
        safe_key = key.replace(".", "_").replace("/", "-")
        if suffix:
            return f"bis_{flow_id}_{version}_{safe_key}_{suffix}.csv"
        return f"bis_{flow_id}_{version}_{safe_key}.csv"

    def _cache_load(self, key: str) -> str | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / key
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning(f"cache read failed for {key}: {e}")
            return None

    def _cache_save(self, key: str, text: str) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / key
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as e:
            log.warning(f"cache write failed for {key}: {e}")
