# Cold-email templates — for operator review, NOT auto-send

Preview-first per discipline rule. Each ≤ 200 words, research peer-to-peer tone, no sales / pitch language. Sequence after SSRN paper goes live (you'll have the link to anchor the email).

---

## Template — Aldasoro (BIS Innovation Hub / Monetary & Economic Department)

**To:** Iñaki Aldasoro <inaki.aldasoro@bis.org>
**Cc:** —
**Subject:** Open-source SRISK / ΔCoVaR / MES reimplementation — interested in feedback

> Dear Dr Aldasoro,
>
> I have been following your work on bank funding and cross-border financial flows, in particular Aldasoro-Ehlers-Eren (2019) on dollar funding and Aldasoro et al. (2022) on global liquidity in non-bank intermediaries.
>
> I have just released CBSRM (Cross-Border Systemic Risk Monitor) — an open-source 7-layer Python platform that reproduces the SRISK / ΔCoVaR / MES triad under one Protocol and one cryptographic audit chain. The implementation is pure-numpy at simulate-time (no SciPy / arch fitting dependency), and the cross-source replication harness in the v0.2 release covers OFR-FSI vs ECB CISS for the US / EA / UK over 2010-2026.
>
> If you have a few minutes, I would value your feedback on either: (a) the cross-jurisdiction integration design, which is the part most relevant to the BIS Innovation Hub's policy-tooling work, or (b) the SRISK / ΔCoVaR / MES implementations against the V-Lab benchmark.
>
> Methodology paper (SSRN): <PASTE SSRN LINK AFTER SUBMISSION>
> Repository: https://github.com/pravo123/cbsrm
>
> Happy to share the audit-chain design doc separately if it would be useful.
>
> With thanks,
> Prabhawa Koirala
> WaverVanir International

---

## Template — Schrimpf (BIS Monetary & Economic Department)

**To:** Andreas Schrimpf <andreas.schrimpf@bis.org>
**Cc:** —
**Subject:** Open-source systemic-risk platform — feedback on cross-asset macro layer

> Dear Dr Schrimpf,
>
> I've been working on a methodology paper for CBSRM (Cross-Border Systemic Risk Monitor), an open-source 7-layer Python platform that pairs the canonical systemic-risk triad (SRISK / ΔCoVaR / MES) with a macro-regime layer covering five jurisdictions including Japan via USD/JPY. The macro layer's USD-regime indicator draws on the Bruno-Shin and Avdjiev-du-Koepke-Shin lineage that your work has extended.
>
> The platform is Apache 2.0 — no commercial intent, no paywall — and ships a fully reproducible audit chain, so every published numerical claim has a verifiable lineage from FRED / OFR / ECB to served value.
>
> If you have time, I would particularly value your view on whether the broad-USD + USD/JPY + DXY regime decomposition is the right cross-asset scope, or whether the platform should extend to commodity FX / EM-vs-DM separately.
>
> Methodology paper (SSRN): <PASTE SSRN LINK AFTER SUBMISSION>
> Repository: https://github.com/pravo123/cbsrm
>
> Many thanks,
> Prabhawa Koirala
> WaverVanir International

---

## Template — V-Lab director / senior research (NYU Stern)

**To:** vlab-research@stern.nyu.edu  *(or specific researcher if known)*
**Subject:** Open-source SRISK reimplementation — cross-validation interest

> Dear V-Lab team,
>
> I have just open-sourced CBSRM, which includes a pure-Python reimplementation of SRISK (Brownlees-Engle 2017) plus ΔCoVaR and MES. The full source is Apache 2.0; the implementation is pure-numpy at simulate-time and validated against four published invariants (independence, perfect correlation, median q, monotonicity in correlation).
>
> Since V-Lab is the canonical reference for SRISK, I would like to cross-validate the CBSRM numbers against your published series for a handful of G-SIBs. If the implementation passes that check, I will note V-Lab as the reference benchmark in the next version of the methodology paper.
>
> Methodology paper (SSRN): <PASTE SSRN LINK AFTER SUBMISSION>
> Repository: https://github.com/pravo123/cbsrm
> Whitepaper §§10–12 cover the risk-pricing layer.
>
> Open to any feedback on the parameter-conventions, particularly the GJR-GARCH-DCC default coefficient set in `cbsrm.risk.garch_dcc_sim`.
>
> Thank you,
> Prabhawa Koirala
> WaverVanir International

---

## Template — Hedge-fund / prop-shop quant CTO (cold)

**To:** <head of risk / quant CTO of target firm>
**Subject:** Open-source SRISK / ΔCoVaR — would value 15 minutes

> Hello,
>
> I built CBSRM — an open-source 7-layer cross-jurisdiction financial-stability and risk-pricing platform that reproduces SRISK / ΔCoVaR / MES under one Protocol with full audit-chain reproducibility. Solo build, in public, methodology-first. github.com/pravo123/cbsrm
>
> The public release covers the academic-canonical surface. The private companion (VolanX) applies the same data / indicators / audit primitives to a multi-broker derivatives execution platform that is currently in paper-trade against Tastytrade.
>
> If <FIRM>'s risk team is doing anything in this space — supervisory-grade audit, cross-jurisdiction systemic-risk monitoring, or multi-broker derivatives infra — I would value a 15-minute conversation. Not a sales pitch — I want to understand whether the platform is solving a real institutional pain or only an academic one.
>
> Happy to send the SSRN paper or the private-side architecture diagram separately.
>
> Best,
> Prabhawa Koirala
> WaverVanir International

---

## Template — Central-bank Innovation Hub (BIS Innovation Hub / equivalent)

**To:** innovation-hub@bis.org *(or specific country's CB Innovation team)*
**Subject:** Open-source cross-border systemic-risk platform — fit for Innovation Hub project pipeline?

> Dear team,
>
> I have released CBSRM (Cross-Border Systemic Risk Monitor), an open-source 7-layer Python platform that consolidates the canonical systemic-risk measures (SRISK / ΔCoVaR / MES) and stress indicators (CISS, OFR-FSI, STLFSI4, ECB CISS for EA/US/UK, plus a 10-indicator macro engine) under one Protocol, one cryptographic audit chain, and one reproducibility guarantee.
>
> The design choices were made specifically for supervisory adoption: full lifecycle event capture, deterministic Monte Carlo, multi-language interpretation labels (EN / JA / ES / FR / DE), and a pure-numpy core that runs on a researcher's laptop and behind a production FastAPI service unchanged.
>
> If the BIS Innovation Hub has a project line on supervisory tooling, cross-border systemic-risk monitoring, or macroprudential infrastructure, I would value a conversation about whether CBSRM could serve as a reference implementation.
>
> Methodology paper (SSRN): <PASTE SSRN LINK AFTER SUBMISSION>
> Repository: https://github.com/pravo123/cbsrm
>
> Thank you for the work the Hub is doing — looking forward to any response.
>
> Prabhawa Koirala
> WaverVanir International

---

## Sending discipline

1. **Do NOT send before the SSRN link exists.** The paper anchors the credibility of the cold email; without it, the message reads as a sales pitch.
2. **Send one per day, max.** Spaced cadence avoids triggering anti-spam heuristics on the receiving end and gives time to respond.
3. **Track every send** — date, recipient, response. A simple Google Sheet is fine.
4. **No follow-up before 10 working days** unless they replied. A single polite follow-up at 10-14 days is standard.
5. **If a response arrives**, switch tone to research-peer-conversation, never sales. The single most important rule.
