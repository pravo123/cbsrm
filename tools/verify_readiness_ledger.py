"""Validate public readiness reporting without accessing private source or fixtures."""
from __future__ import annotations

import json
import re
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "docs/readiness/evidence-2026-10-06.json"


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != "cbsrm-readiness-evidence/1":
        errors.append("unsupported ledger schema")
    seen: set[str] = set()
    for cohort in data.get("independent_cohorts", []):
        if cohort.get("id") in seen:
            errors.append("duplicate cohort")
        seen.add(cohort.get("id"))
        if cohort.get("kind") != "independent_component":
            errors.append("peer evidence mislabeled as independent")
        for field in ("passed", "failed"):
            value = cohort.get(field)
            if type(value) is not int or value < 0:
                errors.append("invalid assertion count")
        for field, length in (("build", 40), ("evidence_sha256", 64)):
            if not re.fullmatch(rf"[0-9a-f]{{{length}}}", cohort.get(field, "")):
                errors.append("missing exact provenance")
    for item in data.get("peer_only", []):
        if item.get("independently_rerun") is not False:
            errors.append("unverified peer rerun claim")
    for family in data.get("release_cases", {}).values():
        p, a = family.get("prepared"), family.get("accepted")
        if type(p) is not int or type(a) is not int or not 0 <= a <= p:
            errors.append("invalid release case count")
    if data.get("full_platform_release_accepted"):
        if any(f["accepted"] != f["prepared"] for f in data["release_cases"].values()):
            errors.append("release claimed with unaccepted cases")
    if any(k in data for k in ("total_product_tests", "total_features_accepted")):
        errors.append("ambiguous aggregate count")
    return errors


if __name__ == "__main__":
    findings = validate(json.loads(LEDGER.read_text(encoding="utf-8")))
    if findings:
        raise SystemExit("\n".join(findings))
    print("Readiness evidence counts and provenance are consistent; no release claim is inferred.")
