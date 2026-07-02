"""Gate: fail (exit 1) if the freshly built current.json is degraded.

Reads site/current.json and requires summary.live >= MIN_LIVE_LENSES (env, default 6).
Wired into .github/workflows/refresh-current.yml BEFORE the commit step: a degraded
snapshot (e.g. FRED key broken -> only the 3 keyless ECB lenses live) turns the run
red (GitHub emails it) and, because the commit step is skipped, the last-good committed
snapshot stays live instead of the site silently publishing 3/8.

Local test:
    MIN_LIVE_LENSES=6 python tools/check_snapshot.py           # against site/current.json
    MIN_LIVE_LENSES=6 python tools/check_snapshot.py some.json  # against an explicit file
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = int(os.environ.get("MIN_LIVE_LENSES", "6"))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    path = Path(argv[0]) if argv else ROOT / "site" / "current.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summ = data.get("summary", {})
    live, total = int(summ.get("live", 0)), int(summ.get("total", 0))
    unavailable = [r.get("id") for r in data.get("readings", []) if r.get("status") != "ok"]
    print(f"live={live}/{total} floor={FLOOR} unavailable={unavailable}")
    if live < FLOOR:
        msg = (f"Degraded snapshot: {live}/{total} lenses live (floor {FLOOR}); "
               f"unavailable={unavailable}. Not committing - last-good snapshot stays live. "
               f"Check FRED_API_KEY / upstream feeds.")
        print(f"::error::{msg}")           # GitHub Actions annotation
        print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
