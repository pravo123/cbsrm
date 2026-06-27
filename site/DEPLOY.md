# Deploying cbsrm.wavervanir.com

This `site/` folder is a **self-contained static website** — no build step, no server,
no external dependencies. Drop it on any static host and point the subdomain at it.

```
site/
  index.html      ← the institutional marketing/sales landing
  terminal.html   ← the live Risk Terminal (self-contained, offline)
  _headers        ← security headers (Cloudflare Pages / Netlify)
  DEPLOY.md       ← this file
```

## Before you publish — fill these in (search `EDIT` / placeholders in `index.html`)

1. **Inbound email** — replace `hello@wavervanir.com` (appears in the CTA, footer,
   and `mailto:` links) with the real address that should receive briefing requests.
2. **Pricing** — the **Desk** tier shows `from $—/yr`. Set your number, or change it to
   "Request a quote". The **Institution** tier is "Custom" (fine as-is).
3. **LinkedIn URL** — confirm `https://www.linkedin.com/company/wavervanir-international/`
   resolves; update if your company page slug differs.
4. (Optional) **GitHub URL** — links point at `github.com/pravo123/cbsrm`; change if the
   public repo moves.

## Option A — Cloudflare Pages (recommended: free, auto-TLS, CDN)

1. Push this repo (or just `site/`) to GitHub, **or** use Direct Upload.
2. Cloudflare dashboard → **Workers & Pages → Create → Pages**.
   - Framework preset: **None**.
   - Build command: *(empty)*. Build output directory: **`site`** (or `/` if you upload `site/` directly).
3. **Custom domains → Set up a custom domain → `cbsrm.wavervanir.com`.**
   - If `wavervanir.com`'s DNS is **already on Cloudflare**, the CNAME is added for you
     and TLS is issued automatically — done.
   - If DNS is **elsewhere** (e.g. Bluehost), add a `CNAME` record:
     `cbsrm` → `<your-project>.pages.dev` (proxied/normal), then finish the custom-domain
     step in Cloudflare. TLS auto-issues + auto-renews.

## Option B — Netlify (also free, auto-TLS)

1. Drag-and-drop the `site/` folder at <https://app.netlify.com/drop>, or connect the repo
   with **base = `site`**, build command empty, publish directory `site`.
2. **Domain settings → Add custom domain → `cbsrm.wavervanir.com`** and follow the DNS
   instructions (a `CNAME` to your `*.netlify.app` target). TLS (Let's Encrypt) auto-issues.

## DNS + TLS notes

- `cbsrm.wavervanir.com` already exists — you only need to repoint it at the static host
  above. Use a `CNAME` (or Cloudflare's automatic record), **not** the old target.
- Pick a host that **auto-renews TLS** (Cloudflare/Netlify both do) so this subdomain does
  not repeat the expired-certificate issue seen on `volanx.wavervanir.com`.

## Next step (optional): the live `/api/pipeline/...` demo

To make the governance snippet on the page real (a `curl`-able, hash-verifiable record),
deploy the read-only API (`cbsrm.api.routes:app`) on a small Python host (Render/Fly free
tier) exposing only the deterministic routes — `/pipeline/{window_id}`, `/pipeline/verify`,
`/reports/crisis-dossiers`, `/reports/macro-composite` (no FRED key required) — and route
`cbsrm.wavervanir.com/api/*` to it. Ask and this can be scaffolded (Dockerfile + host config).

> CBSRM is a risk-**measurement** and model-governance tool — not investment advice.
