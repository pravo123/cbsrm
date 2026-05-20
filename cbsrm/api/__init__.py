"""
cbsrm.api — FastAPI HTTP layer.

Two tiers (planned for v0.x):
  - Public (rate-limited) — methodology results, free re-distribution OK
  - Authenticated (paid) — custom institution lists, real-time feeds,
    audit-chain exports for compliance teams

For v0.1 only the public read endpoints are present.
"""
from cbsrm.api.routes import build_app

__all__ = ["build_app"]
