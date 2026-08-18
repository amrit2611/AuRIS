# AuRIS, Audit Risk Identification System

> **Try it live: [aurisnow.streamlit.app](https://aurisnow.streamlit.app)**
> Upload any transactions CSV or click one of the bundled examples (synthetic 10K rows, or 5,254 real NASA FY2024 federal contracts). AuRIS uses an LLM to auto-map your column names, runs six risk checks, scores every row 0-100, ranks the highest-risk rows into a priority queue, and writes a CFO-readable executive summary. No account, no card.

**AuRIS** is a Python audit-risk tool that ingests a transactions CSV, runs six configurable risk checks (five statistical plus an opt-in Isolation Forest), aggregates the findings into a 0-100 risk score per row, and surfaces them as a CSV report, interactive Plotly visualizations, an AI-generated executive summary, an interactive web dashboard, or an importable library. AuRIS is opinionated about what production-grade engineering looks like: **65 pytest tests + Next.js typecheck + build in CI**, mocked LLM clients (no real API calls), and a live public deploy.

- **Live app:** [aurisnow.streamlit.app](https://aurisnow.streamlit.app)
- **Author:** Amrit Dhandharia
- **Created:** April 2025
- **Repo:** [github.com/amrit2611/AuRIS](https://github.com/amrit2611/AuRIS)

## Four interfaces, one engine

1. **CLI:** `python -m auris -i data/transactions.csv -o output`
2. **Streamlit dashboard:** `streamlit run app.py` (interactive sliders wired to every threshold, deployed at [aurisnow.streamlit.app](https://aurisnow.streamlit.app))
3. **Library:** `from auris.audit_risk import check_duplicates, check_anomalies, ...`
4. **REST API + Next.js frontend:** `uvicorn auris.api:app --port 8000` for the backend; `cd web && npm run dev` for the Next.js 15 + TypeScript + Tailwind frontend. This is the Level 3 full-stack rebuild; deploy target is Railway (backend) + Vercel (frontend). See [`web/README.md`](web/README.md) for the frontend layout and local dev instructions.

## Risk checks

All six checks are tunable through a single `RiskConfig` dataclass and exposed via CLI flags + Streamlit sliders.

### 1. Duplicate Transaction Detection
Identifies transactions with identical `vendor`, `amount`, and `date` (ignoring `invoice_id`). Catches double payments and data-entry errors.
Output: `risk_type = 'Duplicate'`.

### 2. High-Value Anomaly Detection
Flags transactions above a configurable quantile of the `amount` column (default: top 10%).
Tunable via `--anomaly-quantile` (default `0.9`).
Output: `risk_type = 'Anomaly'`.

### 3. Missing Data Detection
Identifies rows with missing values in any column. Supports audit-trail integrity.
Output: `risk_type = 'Missing Data'`.

### 4. Vendor Frequency Analysis
Flags vendors whose transaction count is above a configurable quantile (default: top 10%). Spots overactive vendors.
Tunable via `--vendor-frequency-quantile` (default `0.9`).
Output: `risk_type = 'High Frequency'`.

### 5. Amount Deviation Detection
Per vendor: flags transactions outside `[low_multiplier × mean, high_multiplier × mean]`. Detects unusual payments relative to a vendor's normal range.
Tunable via `--deviation-low` (default `0.2`) and `--deviation-high` (default `2.0`).
Output: `risk_type = 'Amount Deviation'`.

### 6. ML Multivariate Anomalies (opt-in)
Isolation Forest over `(amount, vendor_encoded, date_ordinal)`, seeded for deterministic runs. Catches joint-feature outliers that the statistical checks miss in isolation.
Enable via `--enable-ml`. Tunable via `--ml-contamination` (default `0.05`), `--ml-n-estimators` (default `200`), `--ml-random-state` (default `42`).
Output: `risk_type = 'ML Anomaly'`.

## AI-Augmented Summaries

On top of the six risk checks, AuRIS can generate a CFO-readable Markdown summary of the flagged transactions using an open-weight LLM served via the Groq API. This is opt-in and entirely separate from the statistical pipeline, so the engine itself never depends on a network call.

### How it works

`src/auris/summarize.py` exposes `summarize_risks(report, config)`. It groups the risk report by `risk_type`, takes the top 5 highest-amount rows from each group, and sends that compact projection to Groq (default model: `openai/gpt-oss-120b`). The response is a Markdown document with a 3-5 bullet executive summary plus one paragraph per risk type. Empty reports short-circuit with a canned "no risks found" message and do not call the API.

### Setup

1. Get a free API key at [console.groq.com](https://console.groq.com). No credit card required.
2. Create a `.env` file at the repo root:
   ```bash
   echo 'GROQ_API_KEY=gsk_...' > .env
   ```
3. Install the SDK (already in `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```

Both `python -m auris` and `streamlit run app.py` auto-load `.env` via [python-dotenv](https://github.com/theskumar/python-dotenv), so the key is picked up automatically on every run. The `.env` file and any `*.key` / `secrets.json` are gitignored. Never commit your API key.

### CLI usage

```bash
python3 -m auris -i data/transactions.csv -o output --summarize -v
```

When `--summarize` is set, after the regular pipeline finishes AuRIS writes `output/risk_summary.md` alongside `risks_report.csv` and the five PNG plots. Override the model or token cap with `--summary-model` and `--summary-max-tokens`.

### Streamlit usage

Launch the dashboard as usual:
```bash
streamlit run app.py
```
Under the "AI Executive Summary" section there is a **Generate AI Summary** button. Click it, the summary is generated, rendered as Markdown, and offered as a Markdown download.

### Cost

Groq's free tier covers 14,400 requests per day with no credit card on file, so normal development and demo usage costs nothing. A typical summary call is a few thousand input tokens and under 1024 output tokens. All tests use a mocked Groq client, so CI does not require an API key and incurs no cost.

### Example run on real federal contract data

To show the summary layer working on something other than synthetic data, AuRIS was run against **NASA's FY2024 prime contract awards**, sourced as a public CSV export from [USASpending.gov](https://www.usaspending.gov). After filtering to the fiscal year (Oct 1 2023 through Sep 30 2024), the mapped dataset contained 5,254 contract awards across 2,082 vendors.

A small adapter script converts the raw USASpending CSV to AuRIS's schema:

```bash
# 1. Download the "Awards" ZIP from usaspending.gov Advanced Search (filtered
#    to your desired agency and fiscal year), unzip, save the
#    Contracts_PrimeAwardSummaries CSV to data/usaspending_raw.csv.
# 2. Map its 286 columns down to AuRIS's schema:
python3 scripts/load_usaspending.py \
    -i data/usaspending_raw.csv \
    -o data/usaspending_sample.csv \
    --fiscal-year 2024 -v

# 3. Run AuRIS on the mapped file:
python3 -m auris -i data/usaspending_sample.csv -o output --summarize --enable-ml -v
```

The full generated executive summary is committed at [`examples/nasa_fy2024_summary.md`](examples/nasa_fy2024_summary.md). Selected findings from that run:

- **Lockheed Martin Corp** flagged in both the statistical and ML anomaly checks, with $876M of total exposure across those categories.
- **SpaceX** flagged in four of six risk types (Amount Deviation, Anomaly, High Frequency, ML Anomaly), $851M total.
- **Native Resource Development Co Inc** flagged in five of six risk types despite being a small vendor: cross-check overlap identified it as the highest-priority audit target even though its individual transactions were not the largest.
- **12 duplicate transactions** detected across the 5,254 contracts, most notably a set of repeated payments to Creare LLC.

The mapped dataset (`data/usaspending_sample.csv`) is committed so anyone browsing the repo can reproduce this exact run. The 26MB raw file is gitignored; regenerate it from USASpending as described above.

## Risk Scoring (Level 2)

Raw check output is a flat list of flagged rows tagged with `risk_type`. On real-world data those lists overlap heavily and don't tell an auditor which of the thousands of flagged rows to look at first. **Risk scoring collapses the overlap into a triage queue.**

`src/auris/scoring.py::score_report(report, config)` takes the concatenated report and returns a DataFrame where:

- Each source transaction (identified by `invoice_id`) appears exactly once.
- `risk_score` (0-100) is the sum of the weights of every check that fired on the row, capped at 100.
- `reasons` is the sorted list of check names that contributed.
- Rows are sorted by score descending, so the caller gets a ready-made triage queue.

### Weights (tunable via `RiskConfig`)

Default weights sum to 100 so a row flagged by every check maxes the scale:

| Check | Weight | Rationale |
|---|---|---|
| Duplicate | 25 | Highest-signal audit finding (real double-payments). |
| Anomaly | 20 | Statistical outlier by amount. |
| Amount Deviation | 15 | Per-vendor outlier. |
| ML Anomaly | 20 | Multivariate pattern the statistical checks miss. |
| Missing Data | 10 | Hygiene signal, not fraud. |
| High Frequency | 10 | Noisy on skewed real data; kept low intentionally. |

Override any weight via `RiskConfig(duplicate_weight=..., ...)`.

### Where scoring appears

- **CLI:** `python -m auris ... --summarize` writes `risks_scored.csv` alongside `risks_report.csv`. The AI summary consumes the scored view so its Priority Actions can name specific high-scoring rows.
- **Streamlit dashboard:** a "Priority queue" metric card shows the count of rows with score ≥ 50 (typically ≥ 3 checks fired). The Findings tab shows the scored triage queue with a score-cutoff slider and a per-check filter based on the `reasons` column.
- **Library:** `from auris.scoring import score_report`.

### Example on the bundled NASA FY2024 slice

Running scoring on `data/usaspending_sample.csv`:

- 2,036 raw check hits collapse to 1,660 scored unique rows.
- Top-scored rows (score 65) name specific vendors and describe which checks fired, e.g. `Caltech, $87M, [Amount Deviation, Anomaly, High Frequency, ML Anomaly]`.

## Universal CSV Support (LLM Column Detection)

AuRIS's pipeline internally expects four columns: `vendor`, `amount`, `date`, `invoice_id`. Real-world CSVs almost never come with those exact names. Rather than shipping a hand-written adapter for every possible data source, AuRIS uses the same Groq LLM layer that writes the executive summary to also read your CSV headers (and, when the CSV is not too wide, a few sample rows) and return a mapping.

### How it works

- **CLI:** On every run, AuRIS checks whether the input CSV already has the four required column names. If yes, it proceeds unchanged. If no, it calls `detect_columns` in `src/auris/schema.py`, which sends the headers to the configured Groq model with a strict JSON response schema and applies the returned mapping automatically. All requires `GROQ_API_KEY`.
- **Streamlit dashboard:** After you upload a CSV, if it does not match AuRIS's default schema, a **Column Mapping** section appears with four dropdowns pre-selected with the LLM's guesses. You confirm or override with one click before analysis runs.
- **Manual override on the CLI:** Pass `--column-map "vendor=col1,amount=col2,date=col3,invoice_id=col4"` to skip auto-detection entirely.

### Wide-CSV handling

For CSVs with more than 40 columns (e.g. federal spending exports with 286 columns), AuRIS omits the sample rows from the prompt and asks the LLM to infer the mapping from column names alone. This keeps the request under Groq's free-tier per-request token limit. Individual cell values are also capped at 120 characters so long text descriptions do not blow up the prompt.

### Example: any USASpending export, no adapter script needed

Before LLM column detection, running AuRIS on a raw USASpending file required a hand-written adapter (`scripts/load_usaspending.py`). Now:

```bash
# Download any USASpending Contracts CSV, save to data/usaspending_raw.csv
python3 -m auris -i data/usaspending_raw.csv -o output --summarize -v
```

AuRIS reads the 286 headers, asks Llama to map them, applies the mapping, and runs the pipeline. The `scripts/load_usaspending.py` adapter is now only useful if you want to filter by fiscal year before analysis; column mapping is handled by the LLM.

### Cost

One additional Groq call per run (about 200-400 tokens). At Groq's free-tier rates (14,400 requests per day), this is negligible; it does not affect the "no credit card needed" story.

## Visualizations

Five PNG plots written to the output directory on every run:

1. **`amount_distribution.png`**, histogram of transaction amounts.
2. **`vendor_frequency.png`**, bar chart of transactions per vendor.
3. **`time_series.png`**, scatter of amounts over time with a rolling-mean trend line.
4. **`risk_distribution.png`**, pie chart of risk-type proportions.
5. **`vendor_date_heatmap.png`**, heatmap of transaction density across vendors and dates.

## Requirements

- **Python:** 3.10, 3.11, or 3.12 (CI runs all three on every push)
- **Base dependencies:** pandas, matplotlib, seaborn, scikit-learn
- **Dev dependencies:** pytest (adds to the base)
- **App dependencies:** streamlit (adds to the base)

## Installation

### Clone
```bash
git clone https://github.com/amrit2611/AuRIS.git
cd AuRIS
```

### Virtual environment
```bash
python3 -m venv venv
source venv/bin/activate     # On Windows: venv\Scripts\activate
```

### Install
```bash
pip install -r requirements.txt           # Engine + AuRIS package
pip install -r requirements-dev.txt       # Engine + AuRIS + pytest
pip install -r requirements-app.txt       # Engine + AuRIS + Streamlit dashboard
```

Each `requirements-*.txt` file installs AuRIS itself (via `pyproject.toml`) alongside its dependencies. `python -m auris ...` and `streamlit run app.py` work from any directory afterwards. For local development against a live source tree, use `pip install -e .` instead to install AuRIS in editable mode.

### Optional: generate a synthetic dataset
A seeded 10K-row generator with injected duplicates and outliers is included:
```bash
python3 generate_dataset.py
```
This writes `data/transactions.csv`. The expected schema is `invoice_id, vendor, amount, date, description`.

## Usage

### CLI
```bash
# Default run, statistical checks only
python3 -m auris -i data/transactions.csv -o output -v

# Add the Isolation Forest ML pass
python3 -m auris -i data/transactions.csv -o output --enable-ml -v

# Custom thresholds
python3 -m auris --anomaly-quantile 0.95 --deviation-low 0.1 --deviation-high 3.0 -v
```

### Streamlit dashboard
```bash
streamlit run app.py
```
Opens at `localhost:8501`. All `RiskConfig` thresholds are wired to sliders so you can re-run the analysis interactively.

### Library
```python
import sys
sys.path.insert(0, "src")

import pandas as pd
from auris.audit_risk import check_duplicates, check_anomalies, generate_report
from auris.config import RiskConfig

df = pd.read_csv("data/transactions.csv")
config = RiskConfig(anomaly_quantile=0.95)
print(check_anomalies(df, config))
```

### Outputs
- `risks_report.csv`, consolidated report of all flagged rows with their `risk_type`.
- Five PNG visualizations (see above).

## Configuration

All thresholds live in a single frozen dataclass `RiskConfig` (`src/auris/config.py`). Defaults match the original hardcoded values, so a vanilla run is reproducible:

```python
@dataclass(frozen=True)
class RiskConfig:
    anomaly_quantile: float = 0.9
    vendor_frequency_quantile: float = 0.9
    deviation_low_multiplier: float = 0.2
    deviation_high_multiplier: float = 2.0
    ml_contamination: float = 0.05
    ml_n_estimators: int = 200
    ml_random_state: int = 42
    summary_model: str = "openai/gpt-oss-120b"
    summary_max_tokens: int = 1024
```

Every field is exposed three ways: as a CLI flag, as a Streamlit slider, and as a dataclass argument when using AuRIS as a library.

## Testing and CI

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

65 pytest tests + Next.js typecheck + build cover the six risk checks, the report shape, the ML pass, the AI summary layer, the LLM column-detection layer, the risk-scoring engine, and the FastAPI backend:
- `tests/test_audit_risk.py`, 11 tests on the statistical checks.
- `tests/test_ml_anomalies.py`, 7 tests on the Isolation Forest pass.
- `tests/test_summarize.py`, 6 tests on the Groq summary layer (all mocked, no API calls).
- `tests/test_schema.py`, 17 tests on LLM-driven column detection and the mapping helpers, including regression tests for the wide-CSV path (samples omitted from prompt above 40 columns), cell-value truncation (>120 chars), and malformed LLM responses (non-JSON, non-object, non-string mapping values). All mocked, no API calls.
- `tests/test_scoring.py`, 11 tests on the risk-scoring engine: deduplication by `invoice_id`, weight summation, score cap at 100, sort order, custom-weight overrides, empty input, unknown risk-type warnings, missing-invoice-id fallback, and the top-N helper.
- `tests/test_api.py`, 13 tests on the FastAPI backend using FastAPI's TestClient: health, config, CSV rejection, empty upload, schema-match path (no LLM), LLM detection path (mocked), detection failure surfaces as 422, summarize with and without scored view, summarize error path (503), and `RiskConfigModel` merge behaviour.
- Frontend CI job: `npm run typecheck` and `npm run build` under `web/` on every PR so the Next.js build never regresses.

GitHub Actions runs the full test suite against Python 3.10, 3.11, and 3.12 on every push and pull request to `main` and `dev`. See `.github/workflows/ci.yml`.

## Project layout

```
AuRIS/
├── .github/workflows/ci.yml     # Matrix CI: Python 3.10 / 3.11 / 3.12 + Next.js typecheck/build
├── data/transactions.csv        # 10K synthetic rows (from generate_dataset.py)
├── output/                      # Generated reports + plots (gitignored)
├── src/auris/
│   ├── __init__.py
│   ├── __main__.py              # Entry for `python -m auris`
│   ├── audit_risk.py            # Pipeline: 6 checks, 5 plots, CLI
│   ├── api.py                   # FastAPI backend: /health /config /analyze /summarize
│   ├── scoring.py               # 0-100 risk score per row + reason codes (Level 2)
│   ├── schema.py                # LLM-driven column detection for arbitrary CSVs
│   ├── summarize.py             # Groq/LLM executive summary layer
│   └── config.py                # RiskConfig frozen dataclass
├── tests/                       # 65 pytest tests (engine, scoring, ML, LLM mocked, API)
├── web/                         # Next.js 15 + TypeScript + Tailwind frontend
├── app.py                       # Streamlit dashboard
├── generate_dataset.py          # Synthetic data generator
├── pyproject.toml               # Editable install target
├── requirements.txt             # Base deps
├── requirements-dev.txt         # Adds pytest
├── requirements-app.txt         # Adds streamlit
├── JOURNEY.md                   # Living roadmap: where AuRIS was, is, and is going
└── README.md
```

## Try it live

The fastest way to see AuRIS is to open **[aurisnow.streamlit.app](https://aurisnow.streamlit.app)** and click one of the two example buttons:

- **Synthetic 10K rows**: the bundled fake dataset with injected duplicates, anomalies, and vendor-frequency patterns. Runs in ~2 seconds and lands ~14 rows in the priority queue.
- **Real NASA FY2024 contracts**: 5,254 federal contract awards from usaspending.gov. Real vendor names (Caltech, SpaceX, Lockheed, Boeing), real dollar amounts. Watch the AI summary name specific contractors in its Priority Actions.

Or drop any CSV into the upload zone. AuRIS uses an open-weight LLM via Groq to auto-map column names, so you do not need to rename anything. The tool figures out which column is the vendor, which is the amount, etc.

The dashboard has three tabs:

- **Overview**: priority queue count, flagged pool, five interactive Plotly charts.
- **Findings**: scored triage queue with a minimum-score slider and per-check filter, downloadable as CSV.
- **AI Summary**: one-click Groq call, renders a CFO-readable Markdown summary with named vendors and prioritised actions.

## Roadmap

AuRIS is being built up in shippable levels. Each level is a separate PR, leaves the existing test suite green, and adds a new capability without rewriting the engine. Full trajectory (past, present, future) with commentary lives in **[`JOURNEY.md`](JOURNEY.md)**.

Every level below is a **What / Why / How** triple so the direction is legible without opening any code.

**Shipped**

1. **AI summary layer** ✅
   *What:* CFO-readable Markdown summary of the flagged transactions, generated by a Groq-hosted open-weight LLM (`openai/gpt-oss-120b` default, free tier).
   *Why:* A ranked CSV of 1,400 flagged rows is not something a partner or audit committee reads. A summary turns findings into a briefing.
   *How:* Group the risk report by `risk_type`, send the top-N rows per group to Groq, render the response as Markdown. Opt-in via `--summarize` (CLI) or the "Generate AI Summary" button (Streamlit / Next.js).

2. **Risk scoring engine** ✅
   *What:* Every row gets a 0-100 score plus a `reasons` list; rows scoring ≥ 50 land in a Priority Queue.
   *Why:* "5,000 rows flagged" is not actionable. "These 14 rows scored ≥ 50 with reasons X, Y" is.
   *How:* Deduplicate by `invoice_id`, sum weighted contributions from each of the six checks, cap at 100, sort descending. Weights are `RiskConfig` fields, tunable via CLI, sliders, or API.

3. **Full-stack backend + frontend** ✅
   *What:* FastAPI backend at `src/auris/api.py` exposes `/health`, `/config`, `/analyze`, `/summarize`. Next.js 15 + TypeScript + Tailwind frontend at `web/` consumes it.
   *Why:* Streamlit is a great demo surface, but the "real" product story needs a proper backend contract and a fast, static-exported frontend.
   *How:* Pydantic v2 models mirror the engine's return shapes. Frontend types in `web/src/lib/types.ts` are hand-authored to match. Same pipeline, same tests, new HTTP surface.

**Next up**

4. **Deploy: Railway + Vercel** 🔜
   *What:* Public URL for the FastAPI + Next.js stack, alongside `aurisnow.streamlit.app` (which stays as the free demo).
   *Why:* A recruiter or a prospect should be able to see the full-stack product working without cloning the repo or spinning up uvicorn.
   *How:* Dockerfile at repo root (python:3.11-slim, uvicorn CMD, no `--reload`). Railway for the backend with `GROQ_API_KEY` + `AURIS_CORS_ORIGINS` env vars. Vercel for the frontend with `NEXT_PUBLIC_API_URL` pointing at the Railway URL. ETA: ~4-6 hours.

**Planned**

5. **Persistence + auth + run history**
   *What:* Users sign in (magic link), their uploads persist, they can open prior runs and compare two side by side.
   *Why:* Statelessness stops paying for itself the moment the same person wants to see "how did last quarter look?" or "did fixing that vendor drop the priority queue?".
   *How:* Supabase for auth + Postgres. Row-level security on every table keyed by `tenant_id`. Cache AI summaries so re-opening an old run doesn't re-bill Groq.

6. **ERP integration + production polish**
   *What:* Pull transactions from Tally, Zoho Books, or ERPNext on a schedule instead of asking users to upload CSVs. Sentry + PostHog. Landing page.
   *Why:* The buyer's data lives in an ERP, not on their desktop. A CSV uploader is a demo; a scheduled ERP pull is a product. Indian SME + Tally is the wedge.
   *How:* Per-ERP connector modules with a shared interface. Dedup table on `(tenant_id, source_system, external_id)` so re-syncs don't re-flag the same invoice. Threshold-crossing alerts push to email/webhook.

Explicitly **not** on the roadmap: dark mode (until L6 polish, if it fits in 30 min), user avatars, social features, chat, complex RBAC, blog, mobile app. Each is a week of work that doesn't change the trajectory.

## License

This project is open source. See the repository for license details.
