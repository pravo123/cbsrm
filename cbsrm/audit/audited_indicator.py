"""
AuditedIndicator — thin wrapper that wires audit chain into indicator compute calls.

Wraps any IIndicator-compatible object so every .compute() call writes a
4-row audit lifecycle to the chain:

    REQUESTED → INPUT_FETCHED → COMPUTED → SERVED

The returned IndicatorResult has its audit_row_id field populated with the
COMPUTED row id, so downstream consumers can cite the exact computation
in their own outputs.

If the wrapped indicator raises, an INPUT_MISSING or FAILED row is written
and the exception is re-raised — the chain reflects what actually happened.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from cbsrm.audit.chain import AuditChain, AuditEvent, AuditEventKind
from cbsrm.indicators.base import IIndicator, IndicatorResult

log = logging.getLogger("cbsrm.audit.audited_indicator")


class AuditedIndicator:
    """Wraps an IIndicator and writes a full lifecycle to an AuditChain.

    Parameters
    ----------
    indicator : IIndicator
        Any object implementing the IIndicator protocol (.id, .version,
        .source, .required_series(), .compute(data)).
    audit : AuditChain
        The chain to write to.
    consumer : str, optional
        Free-text identifier of who consumed the value (logged in the
        SERVED row payload). Defaults to "unspecified".
    """

    def __init__(self, indicator: IIndicator, audit: AuditChain,
                 consumer: str = "unspecified") -> None:
        if not isinstance(indicator, IIndicator):
            # Be permissive — protocol check is duck-typed
            for attr in ("id", "version", "source", "required_series", "compute"):
                if not hasattr(indicator, attr):
                    raise TypeError(
                        f"wrapped indicator missing {attr!r} — does not satisfy IIndicator"
                    )
        self.indicator = indicator
        self.audit = audit
        self.consumer = consumer

    @property
    def id(self) -> str:
        return self.indicator.id

    @property
    def version(self) -> str:
        return self.indicator.version

    @property
    def source(self) -> str:
        return self.indicator.source

    def required_series(self) -> list[str]:
        return self.indicator.required_series()

    def compute(self, data: pd.DataFrame, **kwargs: Any) -> IndicatorResult:
        """Run indicator.compute(data) with full audit lifecycle."""
        subject = self.indicator.id

        # 1. REQUESTED
        self.audit.append(AuditEvent(
            kind=AuditEventKind.REQUESTED,
            subject=subject,
            payload={
                "version": self.indicator.version,
                "required_series": self.indicator.required_series(),
                "consumer": self.consumer,
            },
        ))

        # 2. INPUT_FETCHED  (or INPUT_MISSING)
        n_rows = int(len(data)) if data is not None else 0
        cols = list(data.columns) if data is not None else []
        if n_rows == 0:
            self.audit.append(AuditEvent(
                kind=AuditEventKind.INPUT_MISSING,
                subject=subject,
                payload={"reason": "empty input DataFrame",
                         "expected_columns": self.indicator.required_series()},
            ))
            raise ValueError(f"{subject}: empty input DataFrame")

        self.audit.append(AuditEvent(
            kind=AuditEventKind.INPUT_FETCHED,
            subject=subject,
            payload={
                "n_rows": n_rows,
                "n_cols": len(cols),
                "columns": cols,
                "date_min": str(data.index.min()) if n_rows else None,
                "date_max": str(data.index.max()) if n_rows else None,
            },
        ))

        # 3. COMPUTED  (or FAILED)
        try:
            result = self.indicator.compute(data, **kwargs)
        except Exception as e:
            self.audit.append(AuditEvent(
                kind=AuditEventKind.FAILED,
                subject=subject,
                payload={"exception_type": type(e).__name__,
                         "exception_msg": str(e)},
            ))
            raise

        latest_value: float | None = None
        latest_ts: str | None = None
        if result.latest is not None:
            ts, v = result.latest
            latest_ts = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            latest_value = float(v)

        computed_row_id = self.audit.append(AuditEvent(
            kind=AuditEventKind.COMPUTED,
            subject=subject,
            payload={
                "version": self.indicator.version,
                "n_obs": int(result.values.size),
                "latest_ts": latest_ts,
                "latest_value": latest_value,
            },
        ))
        result.audit_row_id = computed_row_id

        # 4. SERVED — caller declares this when the value leaves the boundary;
        # we write it here as the default "served back to caller" event.
        self.audit.append(AuditEvent(
            kind=AuditEventKind.SERVED,
            subject=subject,
            payload={
                "consumer": self.consumer,
                "audit_row_id": computed_row_id,
            },
        ))
        return result
