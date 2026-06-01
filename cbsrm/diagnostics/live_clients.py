"""
Concrete live-data client adapter for crisis dossiers.
======================================================
Feeds :func:`cbsrm.diagnostics.build_crisis_dossier_live` with a real,
injectable data client. Satisfies the builder's ``_LiveClients`` protocol
(``fetch_inputs(start, end) -> dict``).

Honesty constraint (documented in every dossier this produces)
--------------------------------------------------------------
Only the **price-panel** layer is sourced live, from FRED market series
(``SP500``, ``DGS10``). The remaining inputs the dossier needs —
``macro_events`` (release prints with consensus), the interbank network
``L/E/h0``, and ``phase_features`` — have **no public live source**
(consensus prints and bank-level exposure matrices are not on FRED / ECB /
OFR). Those layers come from the pinned crisis-window fixtures and are
labelled as such in the dossier ``sources`` / ``research_notes`` so the
``data_source = "live"`` flag is never mistaken for a fully-live interbank
contagion estimate.

Offline tests inject a fake FRED client; production constructs a real
:class:`cbsrm.data.FREDClient` (which needs ``FRED_API_KEY``).
"""
from __future__ import annotations

import logging
from typing import Any

from cbsrm.diagnostics.crisis_dossiers import _FIXTURES

log = logging.getLogger("cbsrm.diagnostics.live_clients")


# FRED market series used for the live price panel. Both are daily and
# public-domain; SP500 carries a redistribution note but derived analytics
# are unrestricted.
_PRICE_SERIES = {
    "SP500": "SPY_PROXY",
    "DGS10": "TLT_PROXY",
}


class LiveDossierClients:
    """Live-data client adapter for :func:`build_crisis_dossier_live`.

    Parameters
    ----------
    fred :
        A FRED-like client exposing
        ``get_series(series_id, *, observation_start, observation_end)
        -> pandas.Series`` (UTC DateTimeIndex). When ``None`` a real
        :class:`cbsrm.data.FREDClient` is constructed lazily.
    network_window :
        Which pinned crisis-window fixture supplies the non-live layers
        (``macro_events`` / network / ``phase_features``). Defaults to
        ``"2008Q4"``.
    """

    def __init__(self, fred: Any = None, *, network_window: str = "2008Q4"):
        if network_window not in _FIXTURES:
            raise ValueError(
                f"unknown network_window {network_window!r}; "
                f"supported = {sorted(_FIXTURES.keys())}"
            )
        self._fred = fred
        self._network_window = network_window

    def _get_fred(self):
        if self._fred is None:
            from cbsrm.data import FREDClient

            self._fred = FREDClient()
        return self._fred

    def _live_price_panel(self, start: str, end: str) -> dict[str, dict[str, float]]:
        fred = self._get_fred()
        panel: dict[str, dict[str, float]] = {}
        for series_id, panel_name in _PRICE_SERIES.items():
            series = fred.get_series(
                series_id, observation_start=start, observation_end=end,
            )
            mapping: dict[str, float] = {}
            for idx, val in series.items():
                if val is None:
                    continue
                try:
                    fval = float(val)
                except (TypeError, ValueError):
                    continue
                # idx is a pandas Timestamp; normalize to YYYY-MM-DD.
                day = getattr(idx, "strftime", lambda _f: str(idx))("%Y-%m-%d")
                mapping[day] = fval
            if not mapping:
                raise ValueError(
                    f"FRED series {series_id} returned no usable observations "
                    f"for [{start}, {end}]"
                )
            panel[panel_name] = mapping
        return panel

    def fetch_inputs(self, start: str, end: str) -> dict[str, Any]:
        """Return the builder inputs for ``[start, end]``.

        Live: the price panel from FRED. Pinned (fixture): macro events,
        interbank network, and phase features. Raises on FRED failure so
        the builder can fall back to its cache.
        """
        fx = _FIXTURES[self._network_window]
        price_panel = self._live_price_panel(start, end)  # may raise → cache path

        note = (
            "LIVE price panel from FRED (SP500, DGS10). Macro event prints, "
            f"interbank network, and phase features are PINNED from the "
            f"'{self._network_window}' fixture (no public live source for "
            "consensus prints or bank-level exposures)."
        )
        sources = list(fx.sources) + [
            "FRED (St. Louis Fed) — SP500, DGS10 (live price panel)",
        ]
        return {
            "title": f"Live crisis dossier {start}..{end}",
            "period_start": start,
            "period_end": end,
            "shock_summary": fx.shock_summary,
            "research_notes": f"{note}\n\n{fx.research_notes}",
            "sources": sources,
            "macro_events": [dict(e) for e in fx.macro_events],
            "price_panel": price_panel,
            "network_L": [list(row) for row in fx.network_L],
            "network_E": list(fx.network_E),
            "network_h0": list(fx.network_h0),
            "network_seed_label": fx.network_seed_label,
            "phase_features": dict(fx.phase_features),
        }


__all__ = ["LiveDossierClients"]
