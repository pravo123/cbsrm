"""Pure, timestamp-free audit records as specified by frozen contract section 5.2."""
from __future__ import annotations

import hashlib
import json


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(
    name: str, input_sha256: str, params: dict, output: dict, prev_hash: str | None = None,
) -> dict:
    """Hash canonical params/output and link to prev_hash, without IO or timestamps.

    Params and output are JSON-ready values supplied by the caller (including
    None for unavailable ratios when serializing portfolio results to JSON).
    """
    params_sha256 = _digest(params)
    output_sha256 = _digest(output)
    return {
        "name": name,
        "input_sha256": input_sha256,
        "params_sha256": params_sha256,
        "output_sha256": output_sha256,
        "prev_hash": prev_hash,
        "hash": _digest([prev_hash or "", name, input_sha256, params_sha256, output_sha256]),
    }
