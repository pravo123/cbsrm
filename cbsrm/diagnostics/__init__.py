"""
cbsrm.diagnostics — replication, comparison, and crisis-window analysis.

The methodology only matters if it can be cross-validated against canonical
references AND demonstrably picks up real episodes. This subpackage exposes
the comparison + replay primitives the whitepaper §7 promises:

  - replicate(...)               — Pearson, Spearman, MAE, crisis-window breakdown
  - CRISIS_WINDOWS               — 9 canonical episode date ranges
  - CrisisReplay                 — per-window peak / z-score / amplification analyzer
  - replay_all_windows()         — run every overlapping window in one call
  - replay_to_markdown_dossier() — concatenate into a single paper-ready dossier

Used by:
  - CLI: `cbsrm replicate ciss-us ofr-fsi --start 2010-01-01`
         `cbsrm crisis-replay ofr-fsi`
  - Whitepaper §7 (numerical claims)
  - SaaS paid tier (vintage-replay reports for compliance)
"""
from cbsrm.diagnostics.crisis_replay import (
    CrisisReplay,
    CrisisReplayReport,
    replay_all_windows,
    replay_to_markdown_dossier,
)
from cbsrm.diagnostics.replication import (
    CRISIS_WINDOWS,
    ReplicationReport,
    crisis_windows,
    replicate,
)

__all__ = [
    "CRISIS_WINDOWS",
    "ReplicationReport",
    "crisis_windows",
    "replicate",
    "CrisisReplay",
    "CrisisReplayReport",
    "replay_all_windows",
    "replay_to_markdown_dossier",
]
