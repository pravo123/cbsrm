"""
Build a publication-quality HTML version of the whitepaper.

The HTML uses an embedded SSRN-friendly print stylesheet (Times-style serif,
1in margins, page breaks before each ## heading, justified body). Once opened
in a modern browser, "File → Print → Save as PDF" produces a submission-ready
PDF without requiring pandoc or LaTeX.

Usage::

    python tools/build_whitepaper_html.py [--out whitepaper/cbsrm_methodology_v1.html]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import markdown


PRINT_STYLESHEET = """
@page { size: letter; margin: 1in; }
@media print {
  h1 { page-break-after: avoid; }
  h2 { page-break-before: always; page-break-after: avoid; }
  h2:first-of-type { page-break-before: avoid; }
  h3 { page-break-after: avoid; }
  pre, blockquote, table { page-break-inside: avoid; }
}
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Times New Roman", Times, serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #0e1116;
  max-width: 7.5in;
  margin: 0 auto;
  padding: 0.5in;
  text-align: justify;
}
h1, h2, h3, h4 {
  font-family: "Helvetica Neue", Arial, sans-serif;
  color: #0e1116;
  line-height: 1.25;
}
h1 { font-size: 22pt; margin-bottom: 0.2em; }
h1 + p, h1 + blockquote { font-size: 12pt; color: #5a6068; }
h2 { font-size: 16pt; margin-top: 1.4em; border-bottom: 1px solid #d8dde2; padding-bottom: 0.2em; }
h3 { font-size: 13pt; margin-top: 1.1em; }
h4 { font-size: 11.5pt; margin-top: 0.9em; }
p { margin: 0.6em 0; }
pre, code {
  font-family: "JetBrains Mono", "Cascadia Code", Consolas, "Liberation Mono", monospace;
  font-size: 9.5pt;
  background: #f5f6f8;
  border-radius: 3px;
}
pre { padding: 0.7em; overflow-x: auto; border-left: 3px solid #b0b7be; }
code { padding: 0.1em 0.35em; }
pre code { background: transparent; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 10pt; }
th, td { border: 1px solid #c4cad0; padding: 0.35em 0.6em; text-align: left; vertical-align: top; }
th { background: #f0f2f5; font-weight: 600; }
blockquote {
  border-left: 3px solid #d0d4d8;
  padding: 0.2em 0.9em;
  color: #475058;
  font-style: italic;
  margin: 0.7em 0;
}
hr { border: none; border-top: 1px solid #d8dde2; margin: 1.3em 0; }
.title-block { text-align: center; margin: 1.5em 0 2em 0; padding-bottom: 1.5em; border-bottom: 1px solid #d8dde2; }
.title-block h1 { font-size: 24pt; margin-bottom: 0.2em; }
.title-block .subtitle { color: #475058; font-size: 13pt; font-style: italic; }
.title-block .author { margin-top: 0.6em; font-size: 12pt; }
.title-block .meta { color: #748088; font-size: 10pt; margin-top: 0.4em; }
"""


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
{stylesheet}
  </style>
</head>
<body>
  <div class="title-block">
    <h1>{title}</h1>
    <div class="subtitle">{subtitle}</div>
    <div class="author">{author}</div>
    <div class="meta">{meta_line}</div>
  </div>
{body_html}
</body>
</html>
"""


def _strip_first_heading(md: str) -> tuple[str, str]:
    """Pull off the first '# Title' line from the markdown."""
    lines = md.splitlines()
    title = ""
    rest_start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("# "):
            title = line.strip()[2:].strip()
            rest_start = i + 1
            break
    return title, "\n".join(lines[rest_start:])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--in", dest="in_path",
                   default="whitepaper/cbsrm_methodology_v1.md",
                   help="Path to source markdown (default: whitepaper/cbsrm_methodology_v1.md)")
    p.add_argument("--out", dest="out_path",
                   default="whitepaper/cbsrm_methodology_v1.html",
                   help="Path to write rendered HTML")
    p.add_argument("--author", default="Prabhawa Koirala / WaverVanir International")
    p.add_argument("--subtitle",
                   default="A 7-Layer Open-Source Platform for Cross-Border Systemic Risk Monitoring and Risk Pricing")
    p.add_argument("--version", default="v0.5.0 (2026-05-21)")
    args = p.parse_args()

    src_path = Path(args.in_path).resolve()
    if not src_path.exists():
        print(f"ERROR: source not found: {src_path}", file=sys.stderr)
        return 1
    out_path = Path(args.out_path).resolve()

    src_md = src_path.read_text(encoding="utf-8")
    title, body_md = _strip_first_heading(src_md)
    if not title:
        title = "CBSRM Methodology"

    body_html = markdown.markdown(
        body_md,
        extensions=["fenced_code", "tables", "toc", "codehilite"],
    )

    rendered = HTML_TEMPLATE.format(
        title=title,
        stylesheet=PRINT_STYLESHEET,
        subtitle=args.subtitle,
        author=args.author,
        meta_line=f"{args.version} &middot; {src_path.name}",
        body_html=body_html,
    )
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  Open in browser, then File → Print → 'Save as PDF' for SSRN submission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
