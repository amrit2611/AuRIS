# AuRIS pivot: CA-channel, Tally-first, GSTR-2B-aware

**Status:** committed (Oct 2026). Supersedes the roadmap framing in `JOURNEY.md` Level 4+.
**Based on:** 4-angle research completed 2026-10-11; full report at `../reports/AuRIS pivot to SmartKatch alternative.md` (outside repo).
**Trigger:** CA-friend interview with Rohit, who outlined the SmartKatch / OpenText VIM invoice-exception pattern used at a large Indian conglomerate.

## The thesis in one paragraph

AuRIS pivots from "upload any transactions CSV" to **a CA-sellable, Tally and Zoho Books-sync, GSTR-2B-aware invoice-exception layer for Indian MSMEs in the ₹5 Cr-₹100 Cr turnover band**. The customer is a chartered-accountant firm managing 20-80 SME clients. The price band is ₹999-2,999/month per MSME GSTIN or ₹2,999-5,999/month per CA firm (10-25 client GSTINs), annual billing, distributed through ICAI's CMP program and direct CA relationships. The product output stays what it is today: a 0-100 scored, reason-coded triage queue with a Groq-written executive summary. What changes is the input (GSTR-2B feeds and ERP sync, not just a CSV upload) and the rule set (GST-native semantics, not generic statistical checks).

## What AuRIS is NOT becoming

- Not a lower-cost SmartKatch for SAP shops. That market is six-figure dollar, SAP-partner-channel, 6-8 week implementations. Fighting there means fighting OpenText, Zycus, HighRadius, Medius, Vic.ai with no SAP integration muscle.
- Not an OpenText VIM add-on. VIM already ships 40-88 exception types; the enterprise is covered.
- Not a direct-to-MSME-finance-team tool. Research signal is strong that CAs are the gatekeeping buyer in India; standalone products get absorbed into CA-channel platforms (Suvit went to Vyapar).
- Not a Tally replacement. Tally remains the ledger of record; AuRIS reads from it, does not try to replace it.

## Target customer, concretely

- **Who**: a CA firm of 2-10 chartered accountants managing 20-80 Indian MSME clients.
- **Clients' profile**: ₹5-50 Cr turnover, already on Tally or Zoho Books, already filing e-invoices (mandatory above ₹5 Cr aggregate turnover since 2023-08-01, [Notification 10/2023-Central Tax]).
- **Current workflow**: monthly GSTR-2B reconciliation done manually or with Suvit / Clear ClearCapture / AI Accountant.
- **Primary pain**: GST ITC risk under Rule 88D (DRC-01C fires on 20%+ mismatch between GSTR-3B and 2B, 7-day response window). CBIC has blocked ~₹40,000 Cr in ITC on mismatches. Section 43B(h) of the Income Tax Act disallows expenses on MSME payments beyond 45 days.
- **Distribution channel**: ICAI's Committee for Members in Practice (CMP) distributes software to its members at free or discounted rates. Zoho Practice uses this model. Vyapar TaxOne is CMP-listed. First serious channel step is confirming the CMP listing path in writing.

## Rohit's seven rules, mapped to engineering

Rohit shared seven exception rules SmartKatch encodes. They split cleanly into two groups:

### Group A — runs on today's data model (ships first)

| # | Rule | Data needed | Status |
|---|---|---|---|
| 2 | Duplicate invoice ingestion (same vendor + amount + date + invoice date) | vendor, amount, date, invoice_id (already have) | Enhance existing `check_duplicates` with GSTIN + normalized invoice-number + content-hash fingerprint (AI Accountant's published shape). |
| 6 | Vendor GSTIN not captured or not matching vendor master | optional `gstin` column + optional vendor master side-table | New check `check_gstin_validity`. Format regex + checksum. Vendor-master lookup is Phase 2. |

### Group B — requires enterprise/ERP data (ships later, side-table ingest first)

| # | Rule | Data needed | Status |
|---|---|---|---|
| 1 | Invoice date before PO date | PO date column | Needs schema extension. |
| 3 | Posting against blocked vendor code | blocked-vendor list | Needs side-table. |
| 4 | GRN short-qty triggering credit note | GRN quantity | Needs schema extension. |
| 5 | Invoice qty or amount > PO qty / amount | PO quantity / amount | Needs schema extension. |
| 7 | PO at header or line of VIM not fully released | PO release status | SAP-specific; may never ship for Tally shops. |

Engineering sequence (data-model-first, not rules-first):

1. **Extend the input schema** to accept an optional PO / GRN / vendor-master side-table. Current single-CSV path keeps working.
2. **Ship the two Group A rules** that work on today's data model (duplicate + GSTIN format).
3. **Ship Group B rules only** for customers who provide the side-table.
4. **De-prioritise Isolation Forest ML.** It is noise on a 50-invoice/month MSME book. Keep it in the engine; stop pitching it.

## Three non-negotiables from Rohit, translated to architecture

- **Data security at the foundation**: tenant isolation at the database level, encryption at rest with per-tenant keys, SOC 2 Type I inside Year 1 (6-9 months, $20K-50K), processing data in-country. Likely Supabase Mumbai or Railway Mumbai region.
- **Customizability as a selling point**: every rule exposes its thresholds via `RiskConfig` (we already have this). Add a per-tenant rule bank so a CA firm can mute noisy rules per client.
- **Central AI engine**: the Groq Llama summary layer evolves into (a) an explain-the-exception endpoint that turns reason codes into CA-ready English, (b) a learning-threshold layer that watches which exceptions each CA closes without action and auto-tunes tolerance per client, (c) collective-pattern detection across a CA's full client portfolio. Full-model GL coding (AppZen / Vic.ai style) is a Level 5+ ambition; the AppZen TruGreen case took 9 months to reach 60% automation on structured ERP data.

## Phased plan

| Window | What ships |
|---|---|
| **3 months** | 15 CA interviews (not code). Tally XML and Zoho Books API ingestion adapters. Rebuilt duplicate check (GSTIN + normalized invoice# + amount + date + content hash). GSTIN format validator + optional vendor-master lookup. FastAPI endpoint that accepts a monthly purchase register, returns a reason-coded exceptions report. |
| **6 months** | GSTR-2B pull + reconciliation via a GSP reseller partnership (Clear or Masters India, since direct GSP registration is heavy). DRC-01C risk score per vendor. Per-tenant rule bank. Next.js CA dashboard listing all clients by score. ICAI CMP listing pursued. First 20 paying CA firms. |
| **12 months** | Learning-threshold layer. Cross-client pattern detection. SOC 2 Type I started. Optional PO/GRN side-table for ₹50-500 Cr clients. Soft-launch an enterprise-lite tier at ₹15,000-30,000/month, deliberately below Clear/Mysa. Target 100-150 paying CA firms, 2,000-5,000 end-MSME GSTINs under management, ARR ₹1-3 Cr. |

## Risks that must be resolved before major engineering

1. **Demand signal uncertainty.** Public complaints about "Tally lets duplicates in" are quiet. The loud complaint is about GSTN platform duplicates in GSTR-2B. If CAs absorb the pain manually, willingness to pay collapses.
   **Resolve by**: 15 CA interviews before any schema design. Ask specifically how many duplicate / GSTIN exceptions they catch per client per month and what they currently charge for that work.
2. **Channel capture by incumbents.** Vyapar owns Suvit, Clear is at $700M+ valuation, ICAI CMP catalog has aligned products. If CMP listing takes 12+ months or needs enterprise references AuRIS does not have, direct CA sales become the only channel, which is slower.
   **Resolve by**: contacting ICAI CMP directly in the first two weeks and getting the listing bar in writing.
3. **GSTN API access.** Reconciling against GSTR-2B programmatically needs either a GSP license (heavy and slow) or a GSP reseller partnership. Suvit, Clear, Tally all solved this.
   **Resolve by**: pricing a reseller partnership with Clear, Masters India, or another approved GSP before committing to the 2B feature.
4. **Data-security credibility.** Top-tier CA firms will push on tenant isolation, India data residency, SOC 2. Without SOC 2 Type I, enterprise CAs will not sign.
   **Resolve by**: budgeting for SOC 2 Type I in Year 1 and architecting for it from day one.

## Three open questions to clarify with Rohit

- **"Aqqrue"** in Rohit's diagram cannot be matched to a known SAP-adjacent product. The only verifiable Aqqrue is a US QuickBooks CPA studio. Likely Gappify Accrual Cloud, an SAP accrual engine, or an internal ITC name. Confirm before using it anywhere external.
- **SmartKatch's ITC customer status** is anonymous in SmartKatch's own marketing. Plausible match but unverified; do not use as social proof.
- **ICAI CMP listing bar**: ask Rohit if he knows anyone on the CMP committee or can introduce.

## What this document is for

Future AI sessions working on AuRIS read `CLAUDE.md`, `JOURNEY.md`, and this file in that order. `CLAUDE.md` holds the project conventions. `JOURNEY.md` tracks shipped PRs. This file holds the current product direction. When direction changes materially again, add a new section here with the date and reason; do not rewrite history.

The research notes and full report that generated this direction live at `/home/amrit2611/Desktop/amrit/research_notes/AuRIS pivot to SmartKatch alternative/` and `/home/amrit2611/Desktop/amrit/reports/AuRIS pivot to SmartKatch alternative.md`, outside the repo on the author's machine. They are the primary sources; this file is the committed decision.
