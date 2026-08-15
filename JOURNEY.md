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

## Where it is (as of 2026-07-24)

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

### Level 3C: Deploy (next up)

Ship the full stack to real infrastructure so the URL can go on a resume.

- `Dockerfile` at the repo root (python:3.11-slim, `pip install -e .`, uvicorn CMD without `--reload`)
- Railway for the backend, with `GROQ_API_KEY` and `AURIS_CORS_ORIGINS` set as env vars
- Vercel for the frontend, with `NEXT_PUBLIC_API_URL` pointing at the Railway URL
- README "Try it live" section updated with the Vercel URL
- Live smoke test: upload `data/transactions.csv` on the deployed site, confirm priority queue + AI summary work

ETA: ~4-6 hours.

### Level 4: Persistence + auth + history

The point where statelessness stops paying for itself. Users need to see their past runs, compare quarters, and not have their data leak into each other's dashboards.

- Supabase for auth (magic link) + Postgres
- Row-level security on every table (`tenant_id` on runs, scored_rows, summaries)
- Run history view: list of prior uploads with filename, date, top score, priority queue size
- Comparison view: pick two runs, see side-by-side risk profiles
- Persist AI summaries (don't re-bill Groq to re-read the same report)

ETA: 3-4 days.

### Level 5: ERP integration + production polish

The wedge that turns AuRIS from a demo into a product: buyers don't upload CSVs, their data lives in Tally / Zoho Books / ERPNext. Reach into those directly.

- Tally connector (start here; the largest Indian SME audit market lives in Tally)
- Zoho Books connector (REST API, well-documented)
- ERPNext connector (open source, easy to sandbox)
- Deduplication table: `(tenant_id, source_system, external_id)` so re-syncs don't re-flag the same invoice
- Continuous auditing: cron-driven pull, alert when a row's risk score crosses a threshold
- Observability: Sentry for backend errors, PostHog for frontend usage
- Landing page + docs site

ETA: ~1 week for a first-pass Tally connector + observability; longer for the rest.

### What we're deliberately not building

Dark mode (until L5, if 30 min), user profiles with avatars, social features, chat, complex RBAC, fancy animations, blog, mobile app. Each is a week of work that doesn't change the project's trajectory.

## How this document works

- Update **"Where it is"** on every level completion.
- Update **"Where it's going"** whenever the next level's scope changes (or a level slips).
- Keep the **"Where it was"** section as-is. It's the origin story; it shouldn't churn.
- If `README.md` and `JOURNEY.md` disagree on shipped features, trust `JOURNEY.md` if this file has been updated more recently, otherwise trust `README.md`.
