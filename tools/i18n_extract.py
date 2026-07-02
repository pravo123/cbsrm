"""Extract the canonical EN i18n dictionary from site/index.html + site/explorer.html.

Collects:
  - innerHTML of every element carrying data-i18n="key"
  - the inline I18N.en JS/data keys (js.*, data.*, ex.*) from both <script> blocks
  - _title / _desc from <title> and <meta name=description>
  - data.preset.<quarter> labels from site/history.json

Writes .tmp_i18n/en.json (temp build artifact — not committed).
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # repo root (script lives in tools/)
OUT = ROOT / ".tmp_i18n"
OUT.mkdir(exist_ok=True)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class Extractor(HTMLParser):
    """Capture raw innerHTML of every element with a data-i18n attribute."""

    def __init__(self, raw: str):
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.out: dict[str, str] = {}
        self.stack: list[dict] = []  # {key, tag, depth, start}

    def handle_starttag(self, tag, attrs):
        if self.stack and tag == self.stack[-1]["tag"] and tag not in VOID:
            self.stack[-1]["depth"] += 1
        d = dict(attrs)
        if "data-i18n" in d and tag not in VOID:
            end_of_open = self.raw.index(">", self.getpos_offset()) + 1
            self.stack.append({"key": d["data-i18n"], "tag": tag,
                               "depth": 0, "start": end_of_open})

    def handle_endtag(self, tag):
        if not self.stack or tag != self.stack[-1]["tag"]:
            return
        top = self.stack[-1]
        if top["depth"] > 0:
            top["depth"] -= 1
            return
        close_at = self.getpos_offset()
        self.out[top["key"]] = self.raw[top["start"]:close_at]
        self.stack.pop()

    def getpos_offset(self) -> int:
        line, col = self.getpos()
        lines = self.raw.split("\n")
        return sum(len(l) + 1 for l in lines[: line - 1]) + col


def extract_file(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8")
    ex = Extractor(raw)
    ex.feed(raw)
    keys = dict(ex.out)

    # inline I18N.en JS keys: "key":"value" pairs inside the en:{...} block
    m = re.search(r"en:\{(.*?)\n\s*\},\n\s*ja:\{\}", raw, re.S)
    if m:
        for k, v in re.findall(r'"((?:js|data|ex)\.[^"]+)":"((?:[^"\\]|\\.)*)"', m.group(1)):
            keys[k] = v.replace('\\"', '"')

    tm = re.search(r"<title>(.*?)</title>", raw, re.S)
    if tm:
        keys["_title"] = tm.group(1).strip()
    dm = re.search(r'<meta name="description" content="([^"]*)"', raw)
    if dm:
        keys["_desc"] = dm.group(1)
    return keys


index_keys = extract_file(ROOT / "site" / "index.html")
explorer_keys = extract_file(ROOT / "site" / "explorer.html")

# preset labels (data-driven, translated via data.preset.<quarter> overrides)
hist = json.loads((ROOT / "site" / "history.json").read_text(encoding="utf-8"))
preset_keys = {f"data.preset.{p['quarter']}": p["label"] for p in hist.get("presets", [])}

bundle = {
    "index": index_keys,
    "explorer": explorer_keys,
    "presets": preset_keys,
}
(OUT / "en.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2),
                             encoding="utf-8")
print(f"index: {len(index_keys)} keys | explorer: {len(explorer_keys)} keys | presets: {len(preset_keys)}")
print("missing-suspects (empty values):",
      [k for d in (index_keys, explorer_keys) for k, v in d.items() if not v.strip()])
