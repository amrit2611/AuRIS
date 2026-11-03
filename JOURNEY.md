# AuRIS Journey

Where AuRIS was, where it is, and where it's going. Updated on every level completion. If this file and `README.md` disagree, `JOURNEY.md` describes the trajectory and `README.md` describes the current shipped surface.

## Where it was

AuRIS started as a ~200-line Python script that read a transactions CSV, ran a handful of anomaly heuristics, and printed the flagged rows. No package structure, no tests, no config surface, no UI. The value was already there (someone could paste a CSV and get useful output), but the code was a single file with no way to grow.

Between April and June 2026 the script got real bones:

- **Restructure** (PR #4): moved the code into `src/auris/`, added `python -m auris` entry, made it installable.
- **Synthetic dataset** (PR #5): 10,000-row transactions CSV so the pipeline had a stable target for testing and demos.
- **Portfolio polish** (PR #8): type hints on every function, structured logging via a named logger (no more `print`), `RiskConfig` frozen dataclass, pytest suite, GitHub Actions matrix on Python 3.10 / 3.11 / 3.12.
- **Isolation Forest** (PR #9, rebuild of closed #6): added the sixth risk check, opt-in via `--enable-ml`, seeded for determinism.
- **Streamlit dashboard** (PR #7, then #20 / #22 / #24 polish): every `RiskConfig` field wired to a slider, five plots rendered inline, deployed free on Streamlit Community Cloud.

By late June the engine was a solid Python package with a live dashboard. That's the "polished script" starting point for the roadmap below.

## Where it is (as of 2026-07-24; deploy since shipped)

Six risk checks, a 0-100 scoring engine, LLM column detection, an AI executive summary, three interfaces backed by one engine, and 65 tests.

### The engine

| Piece | File | What it does |
|---|---|---|
| Six risk checks | `src/auris/audit_risk.py` | Duplicates, high-value anomalies, missing data, high-frequency vendors, per-vendor amount deviation, ML anomalies (Isolation Forest) |
| RiskConfig | `src/auris/config.py` | Frozen dataclass, ~15 tunables with sensible defaults |
| Scoring | `src/auris/scoring.py` | Deduplicates by `invoice_id`, sums weighted contributions from each check, caps at 100, sorts descending. Rows ≥ 50 go in the priority queue. |
| LLM column detection | `src/auris/schema.py` | If the CSV isn't already `vendor / amount / date / invoice_id`, ships column names + samples to Groq/Llama and gets back a mapping. Any CSV works. |
| AI summary | `src/auris/summarize.py` | Groups the risk report by risk type, sends top-N rows per type to Groq/Llama, returns markdown. |

### Three interfaces, one engine

1. **CLI**: `python -m auris -i data/transactions.csv -o output [--enable-ml] [--summarize]`
2. **Streamlit dashboard** (`app.py`): local + hosted at `aurisnow.streamlit.app`
3. **FastAPI backend + Next.js 15 frontend** (`src/auris/api.py`, `web/`): the "real" product surface

All three call the same engine functions. Adding a fourth is trivial.

### Stack (current)

- **Engine**: Python 3.10+, pandas, scikit-learn
- **LLM**: Groq API serving `llama-3.3-70b-versatile`, free tier (14,400 req/day)
- **Backend**: FastAPI + Pydantic v2 + uvicorn
- **Frontend**: Next.js 15 (app router) + TypeScript strict + Tailwind CSS 3.4
- **Dashboard**: Streamlit
- **Tests**: 65 pytest tests across engine, scoring, ML, LLM (mocked), API (TestClient)
- **CI**: GitHub Actions matrix (Python 3.10 / 3.11 / 3.12) + Next.js typecheck & build

### What's shipped

| Level | Scope | Status |
|---|---|---|
| 1 | AI summary layer (Groq/Llama 3.3 70B, `--summarize`, mocked tests, Streamlit button) | ✅ Shipped (PR #12 → #14) |
| 2 | Risk scoring engine (0-100 per row + reason codes) | ✅ Shipped (PR #25) |
| 3A | FastAPI backend (`/health`, `/config`, `/analyze`, `/summarize`) | ✅ Shipped (PR #28) |
| 3B | Next.js 15 + Tailwind frontend | ✅ Shipped (PR #29) |
| Bonus | LLM column detection (any CSV, no adapter script needed) | ✅ Shipped (PR #18) |
| Bonus | Vectorized pipeline for real-world wide CSVs | ✅ Shipped (PR #23) |

## Where it's going

### Direction change (November 2026): AI ledger review

The generic "upload any transactions CSV, run six checks" engine is shipped and live (Level 3C, the deploy, landed on Render + Vercel). The next stage changes what AuRIS is for.

**AuRIS is becoming an AI review layer for accounting ledgers.** It reads a company's full books (purchase vouchers with line items, payments, GST return data) the way a reviewing accountant does, and flags two kinds of problems:

- **Rule breaks**, caught cheaply and exactly: duplicate invoices, invalid GSTINs, PO and GRN out of order, wrong GST type or rate, TDS not deducted, late payments to MSME vendors, GSTR-2B mismatches.
- **Judgment calls**, where AI earns its place: blocked input tax credit under Section 17(5), capital purchases booked as expenses, wrong ledger heads, vendor pricing and billing shifts, invoices split under an approval limit, and risks visible only across several companies' books.

Why the change: pure rule checks on single documents are increasingly built into accounting software itself. The harder and more valuable work is the reviewer's: reading what was actually bought, in context, across months and across companies. The first target is Indian SME books kept in Tally or Zoho Books; the engine stays general, and flags are selectable per company.

What stays: the scoring idea (every finding ranked and explained), the FastAPI + Next.js stack, `RiskConfig`-style configurability, the test discipline. What changes: the input (a real ledger model instead of a flat CSV), the checks (GST, TDS and document semantics instead of generic statistics), and the role of the LLM (from writing a summary to reading every line item).

### Phases

1. **Realistic labelled test ledger** (in progress): synthetic FY 2025-26 books shaped like real exports, with every planted problem and every legitimate look-alike recorded as ground truth.
2. **Ledger data model + ingestion:** one internal model; adapters for Tally exports, Zoho Books exports and GSTR-2B JSON.
3. **Rule layer + evaluation harness:** deterministic checks, each scored for precision and recall against the ground truth.
4. **AI review layer:** every line item read in context, vendor / ledger / price profiles, the model able to query the ledger itself, structured flags with evidence.
5. **Multi-company review, configurable flags, feedback learning.**
6. **Persistence, auth, scheduled sync, observability** (absorbs the old Level 4 and Level 5).

The old Level 4 (persistence + auth + history) and Level 5 (ERP integration + polish) are folded into phases 2 and 6 above.

### What we're deliberately not building

Dark mode (until L5, if 30 min), user profiles with avatars, social features, chat, complex RBAC, fancy animations, blog, mobile app. Each is a week of work that doesn't change the project's trajectory.

## How this document works

- Update **"Where it is"** on every level completion.
- Update **"Where it's going"** whenever the next level's scope changes (or a level slips).
- Keep the **"Where it was"** section as-is. It's the origin story; it shouldn't churn.
- If `README.md` and `JOURNEY.md` disagree on shipped features, trust `JOURNEY.md` if this file has been updated more recently, otherwise trust `README.md`.
