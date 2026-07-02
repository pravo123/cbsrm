"""Validate translated dictionaries and embed them into the site pages.

Usage:
  python _i18n_embed.py validate   # deterministic QA vs en.json (no writes)
  python _i18n_embed.py embed      # validate, then inject dicts into both HTML files

Validation per language (ja/es/fr/de):
  - strict-JSON parse
  - key completeness vs the en.json bundle (index+explorer+presets; explorer
    _title/_desc expected under ex._title/ex._desc)
  - HTML tag multiset preserved per key (tags may move, not appear/disappear)
  - {n}/{t} placeholders preserved
  - protected terms present when present in EN
  - no raw '&' that isn't an entity (breaks innerHTML round-trip)

Embed:
  index.html    <- all keys except ex.* and data.preset.*
  explorer.html <- ex.* (ex._title -> _title), data.*, presets
Replaces the `  ja:{},es:{},fr:{},de:{}` placeholder line inside each page's
I18N literal. Idempotent: re-running overwrites previously embedded dicts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # repo root (script lives in tools/)
TMP = ROOT / ".tmp_i18n"
LANGS = ["ja", "es", "fr", "de"]

PROTECTED = ["CBSRM", "SRISK", "ΔCoVaR", "DebtRank", "CISS", "STLFSI4",
             "SHA-256", "SR 26-2", "Apache-2.0", "PipelineRecord", "FRED",
             "ECB", "VIX", "{n}", "{t}"]

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_OK = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#x[0-9a-fA-F]+);")


def load_en() -> dict[str, str]:
    bundle = json.loads((TMP / "en.json").read_text(encoding="utf-8"))
    flat: dict[str, str] = {}
    flat.update(bundle["index"])
    for k, v in bundle["explorer"].items():
        # explorer page metadata lives under ex._title / ex._desc in the flat map
        flat["ex." + k if k in ("_title", "_desc") else k] = v
    flat.update(bundle["presets"])
    return flat


def tag_multiset(s: str) -> list[str]:
    return sorted(TAG_RE.findall(s))


def bad_amps(s: str) -> int:
    return len([m for m in re.finditer(r"&", s) if not ENTITY_OK.match(s[m.start():])])


def validate() -> tuple[bool, dict[str, dict]]:
    en = load_en()
    ok_all = True
    report: dict[str, dict] = {}
    for lang in LANGS:
        p = TMP / f"{lang}.json"
        entry: dict = {"missing": [], "tag_mismatch": [], "placeholder": [],
                       "protected": [], "raw_amp": [], "extra": []}
        try:
            tr = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            report[lang] = {"fatal": f"JSON parse failed: {e}"}
            ok_all = False
            continue
        for k, env in en.items():
            if k not in tr or not str(tr[k]).strip():
                entry["missing"].append(k)
                continue
            tv = str(tr[k])
            en_tags, tv_tags = tag_multiset(env), tag_multiset(tv)
            if en_tags != tv_tags:
                # allow dropped HTML comments (pr.p carries an EDIT note)
                en_nc = [x for x in en_tags if not x.startswith("<!--")]
                if en_nc != tv_tags:
                    entry["tag_mismatch"].append(k)
            for ph in ("{n}", "{t}"):
                if ph in env and ph not in tv:
                    entry["placeholder"].append(f"{k}:{ph}")
            for term in PROTECTED:
                if term in env and term not in tv:
                    entry["protected"].append(f"{k}:{term}")
            if bad_amps(tv):
                entry["raw_amp"].append(k)
        entry["extra"] = [k for k in tr if k not in en]
        problems = {k: v for k, v in entry.items() if v and k != "extra"}
        report[lang] = entry
        status = "OK" if not problems else f"PROBLEMS {sum(len(v) for v in problems.values())}"
        print(f"[{lang}] {len(tr)} keys — {status}")
        for kind, items in problems.items():
            print(f"    {kind}: {items[:12]}{' …' if len(items) > 12 else ''}")
        if problems:
            ok_all = False
    return ok_all, report


PLACEHOLDER = "  ja:{},es:{},fr:{},de:{}\n};"
EMBEDDED_RE = re.compile(r"  ja:\{.*?\n\};", re.S)


def js_dict(d: dict[str, str]) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def embed() -> None:
    en = load_en()
    trs = {lang: json.loads((TMP / f"{lang}.json").read_text(encoding="utf-8"))
           for lang in LANGS}

    def subset(tr: dict[str, str], page: str) -> dict[str, str]:
        out = {}
        for k, v in tr.items():
            if k not in en or not str(v).strip():
                continue
            if page == "index":
                if k.startswith("ex.") or k.startswith("data.preset."):
                    continue
                out[k] = v
            else:  # explorer
                if k.startswith("ex._title"):
                    out["_title"] = v
                elif k.startswith("ex._desc"):
                    continue  # explorer applyLang does not swap meta description
                elif k.startswith("ex.") or k.startswith("data."):
                    out[k] = v
        return out

    for page, fname in (("index", "index.html"), ("explorer", "explorer.html")):
        path = ROOT / "site" / fname
        raw = path.read_text(encoding="utf-8")
        block = "  " + ",\n  ".join(
            f"{lang}:{js_dict(subset(trs[lang], page))}" for lang in LANGS
        ) + "\n};"
        if PLACEHOLDER in raw:
            raw = raw.replace(PLACEHOLDER, block, 1)
        else:
            raw, n = EMBEDDED_RE.subn(block, raw, count=1)
            if not n:
                raise SystemExit(f"{fname}: no I18N placeholder or embedded block found")
        path.write_text(raw, encoding="utf-8")
        sizes = {lang: len(subset(trs[lang], page)) for lang in LANGS}
        print(f"{fname}: embedded {sizes} keys, {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "validate"
    ok, _ = validate()
    if mode == "embed":
        if not ok:
            raise SystemExit("validation failed — not embedding")
        embed()
    elif not ok:
        raise SystemExit(1)
