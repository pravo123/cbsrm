# SSRN Submission Checklist — CBSRM Methodology Paper

**Goal:** upload `cbsrm_methodology_v1.pdf` to SSRN's Risk Management & Analysis of Risk eJournal (FEN network), with abstract / JEL codes / keywords from `SSRN_SUBMISSION.md`. ETA 15 minutes once you sit down at your machine.

---

## Step 0 — Get a PDF

Three paths, pick whichever is fastest for you:

### Path A — DOCX → Word → PDF *(easiest)*

The build pipeline already produced a clean Word version:

```
cbsrm/whitepaper/cbsrm_methodology_v1.docx
```

1. Open it in Microsoft Word (or LibreOffice / Pages — anything that can save DOCX as PDF)
2. File → Save As → PDF
3. Save to `cbsrm/whitepaper/cbsrm_methodology_v1.pdf`

### Path B — HTML → browser → PDF

Pre-rendered HTML:

```
cbsrm/whitepaper/cbsrm_methodology_v1.html
```

1. Open in Chrome / Edge / Firefox
2. Ctrl+P (or Cmd+P)
3. Destination: "Save as PDF"
4. Paper size: Letter, Margins: Default, Background graphics: ON
5. Save to `cbsrm/whitepaper/cbsrm_methodology_v1.pdf`

### Path C — Pandoc + LaTeX *(if you have it installed)*

```bash
cd cbsrm
pandoc whitepaper/cbsrm_methodology_v1.md \
    -o whitepaper/cbsrm_methodology_v1.pdf \
    --pdf-engine=xelatex \
    --variable=mainfont:"Times New Roman" \
    --variable=fontsize:11pt \
    --variable=geometry:"margin=1in" \
    --metadata title="CBSRM: A 7-Layer Open-Source Platform for Cross-Border Systemic Risk Monitoring and Risk Pricing" \
    --metadata author="Prabhawa Koirala" \
    --metadata date="2026-05-21" \
    --table-of-contents \
    --number-sections
```

Note: in this session, pandoc 3.9 was installed via `pip install pypandoc-binary` but no LaTeX engine (xelatex / pdflatex) was on the system. If you want to use Path C, install MiKTeX (Windows) or BasicTeX (macOS) first.

---

## Step 1 — Open the SSRN submission form

URL: https://hq.ssrn.com → log in (free account if you don't have one) → "Submit a paper".

---

## Step 2 — Paste fields from `SSRN_SUBMISSION.md`

Open `cbsrm/SSRN_SUBMISSION.md` in another tab. Copy each section into the corresponding SSRN form field:

| SSRN field | Copy from `SSRN_SUBMISSION.md` |
|------------|-------------------------------|
| Title | "## Title" section |
| Author | "## Authors" section (just your name; your contact info auto-fills from your SSRN profile) |
| Abstract | "## Abstract" section (under 1500 chars; pre-verified) |
| Keywords | "## Keywords" section — paste all 12 |
| JEL codes | "## JEL codes" section — at minimum the 3 primary (G01, G18, G28) |
| Network | FEN: Financial Economics Network |
| Topic / sub-network | Risk Management & Analysis of Risk eJournal |
| Date | 2026-05-21 (the version date) |
| Manuscript file | upload the PDF from Step 0 |
| Cover letter | "## Cover letter" section |
| Code availability | "## Code availability statement" section |
| Funding | "## Funding statement" section |
| Conflict of interest | "## Conflict of interest statement" section |

---

## Step 3 — Submit

Click Submit. SSRN typically replies within 1-3 business days with a working paper ID (format: SSRN-id-1234567).

---

## Step 4 — Capture the SSRN URL

When the paper goes live, it'll have a URL like `https://ssrn.com/abstract=1234567`. Copy that URL.

---

## Step 5 — Trigger the downstream cadence

With the SSRN URL in hand, the rest of the cashflow loop opens up:

1. **Edit `COLD_EMAILS.md`** — replace every `<PASTE SSRN LINK AFTER SUBMISSION>` placeholder with the real URL
2. **Update the LinkedIn drafts** in `LINKEDIN_DRAFTS.md` — add the SSRN link as the last line of each post
3. **Send the first cold email** — Aldasoro template, per the rate-limit / cadence rules at the bottom of `COLD_EMAILS.md`
4. **Post Draft 1** to LinkedIn (the v0.3 / Japan / i18n release post is the strongest opener)
5. **Add the SSRN link to the GitHub README** — replace the placeholder citation block

---

## Common SSRN gotchas

- **Abstract > 1500 chars** — the abstract in `SSRN_SUBMISSION.md` is pre-trimmed to fit; if you edit it, recount
- **PDF too large** — under 10MB is fine; ours is well below
- **Affiliation field** — put "Independent / WaverVanir International" (SSRN allows independent authors)
- **Co-authors** — leave blank
- **Existing version** — first submission, so no "this revises..." link
- **Embargo** — none; CBSRM is already public on GitHub

---

## After it's accepted

SSRN sends a notification email with the working paper ID. From that moment:

- Open `COLD_EMAILS.md` and walk through the send sequence (one email per day, max)
- Pin the CBSRM repo to your GitHub profile if you haven't already
- Post LinkedIn Draft 1 (the v0.3 release post)
- Update memory: `~/.claude/projects/.../memory/MEMORY.md` — add a note that the SSRN paper is live
