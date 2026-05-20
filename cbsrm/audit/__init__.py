"""
cbsrm.audit — regulator-grade tamper-evident audit chain.

Ports the production audit-log design from WaverVanir's internal
VolanX derivatives risk infrastructure. Public + Apache-2.0.

Used by:
  - cbsrm.indicators — wrap any indicator with AuditedIndicator to write a
    REQUESTED → INPUT_FETCHED → COMPUTED → SERVED lifecycle on every compute.
  - cbsrm.api — every served value carries the audit row ID so external
    users can independently fetch the underlying inputs + methodology
    version that produced it.
  - Regulator-grade SaaS tier (planned) — chain-export for compliance
    workflows.
"""
from cbsrm.audit.audited_indicator import AuditedIndicator
from cbsrm.audit.chain import AuditChain, AuditEvent, AuditEventKind, HAPPY_PATH

__all__ = [
    "AuditChain", "AuditEvent", "AuditEventKind", "HAPPY_PATH",
    "AuditedIndicator",
]
