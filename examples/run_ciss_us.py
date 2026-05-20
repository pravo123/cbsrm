"""
End-to-end CISS-US demo.

Pulls real US public data from FRED, builds the 15-input matrix, runs
CISSUSCanonical, prints the latest reading + every input's source,
verifies the audit chain, and (optionally) dumps the full audit export
to JSON.

Run:
    export FRED_API_KEY=your_free_fred_key
    python examples/run_ciss_us.py
    python examples/run_ciss_us.py --start 2020-01-01 --end 2020-07-01
    python examples/run_ciss_us.py --audit-db ./audit.db --export-audit

Equivalent of:
    cbsrm ciss-us --verbose --audit-db ./audit.db

This is the reference invocation for the methodology in the whitepaper.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

from cbsrm.audit import AuditChain, AuditedIndicator
from cbsrm.builders import CISSUSBuilder
from cbsrm.data import FREDClient
from cbsrm.indicators import CISSUSCanonical


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute CISS-US end-to-end from FRED")
    p.add_argument("--api-key", default=os.environ.get("FRED_API_KEY"))
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--frequency", default="w",
                   help="FRED aggregation: d/w/m/q/sa/a. Default w.")
    p.add_argument("--audit-db", default=None,
                   help="Path to SQLite audit chain DB. If omitted, in-memory only.")
    p.add_argument("--export-audit", action="store_true",
                   help="Print the full audit chain export for CISS-US-Canonical")
    args = p.parse_args(argv)

    if not args.api_key:
        print("FRED_API_KEY env var or --api-key required", file=sys.stderr)
        print("Register free at https://fredaccount.stlouisfed.org/", file=sys.stderr)
        return 1

    # 1. FRED → 15-input matrix
    fred = FREDClient(api_key=args.api_key)
    builder = CISSUSBuilder(fred)
    print(f"[1/4] fetching {len(builder.required_fred_series())} FRED series", file=sys.stderr)
    df, manifest = builder.build(
        start=args.start, end=args.end, frequency=args.frequency,
    )
    if df.empty:
        print(f"[error] no usable rows. warnings: {manifest.warnings}", file=sys.stderr)
        return 2
    print(
        f"[2/4] built {len(df)}-row × {len(df.columns)}-col input matrix "
        f"({manifest.n_substitutes()} substitutes)",
        file=sys.stderr,
    )

    # 2. Audit chain
    if args.audit_db:
        conn = sqlite3.connect(args.audit_db)
    else:
        conn = sqlite3.connect(":memory:")
    audit = AuditChain(conn)

    # 3. CISS-US-Canonical via AuditedIndicator
    indicator = AuditedIndicator(
        CISSUSCanonical(), audit, consumer="example:run_ciss_us",
    )
    print("[3/4] computing CISS-US-Canonical", file=sys.stderr)
    result = indicator.compute(df)

    # 4. Verify chain
    ok, broken = audit.verify()
    print(f"[4/4] audit chain ok={ok} broken={broken}", file=sys.stderr)

    if result.latest is None:
        print("[error] no values produced", file=sys.stderr)
        return 3
    ts, value = result.latest

    out = {
        "indicator_id": result.indicator_id,
        "version": result.version,
        "as_of": ts.isoformat(),
        "value": value,
        "audit_row_id": result.audit_row_id,
        "audit_chain_ok": ok,
        "n_obs": int(result.values.size),
        "subindex_latest": (
            result.subindex_values.iloc[-1].to_dict()
            if result.subindex_values is not None and not result.subindex_values.empty
            else {}
        ),
        "manifest": manifest.as_dict(),
        "interpretation": result.metadata.get("interpretation"),
    }
    print(json.dumps(out, indent=2, default=str))

    if args.export_audit:
        print("\n--- audit chain ---", file=sys.stderr)
        for row in audit.export_for_subject("CISS-US-Canonical"):
            print(json.dumps(row, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
