# AuRIS, Audit Risk Identification System

**AuRIS** is a Python audit-risk tool that ingests a transactions CSV, runs six configurable risk checks (five statistical plus an opt-in Isolation Forest), and surfaces the findings as a CSV report, five visualizations, an interactive web dashboard, or an importable library. Inspired by the auditing needs of large corporations, AuRIS detects duplicates, anomalies, missing data, and unusual vendor patterns and is built to be extended toward an AI-augmented audit platform.

- **Author:** Amrit Dhandharia
- **Created:** April 2025
- **Repo:** [github.com/amrit2611/AuRIS](https://github.com/amrit2611/AuRIS)

## Three interfaces, one engine

1. **CLI:** `python -m auris -i data/transactions.csv -o output`
2. **Streamlit dashboard:** `streamlit run app.py` (interactive sliders wired to every threshold)
3. **Library:** `from auris.audit_risk import check_duplicates, check_anomalies, ...`

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

On top of the six risk checks, AuRIS can generate a CFO-readable Markdown summary of the flagged transactions using the Google Gemini API. This is opt-in and entirely separate from the statistical pipeline, so the engine itself never depends on a network call.

### How it works

`src/auris/summarize.py` exposes `summarize_risks(report, config)`. It groups the risk report by `risk_type`, takes the top 5 highest-amount rows from each group, and sends that compact projection to Gemini (default model: `gemini-2.0-flash-001`, free tier). The response is a Markdown document with a 3-5 bullet executive summary plus one paragraph per risk type. Empty reports short-circuit with a canned "no risks found" message and do not call the API.

### Setup

1. Get a free API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). No credit card required.
2. Set it as an environment variable, or create a `.env` file at the repo root:
   ```bash
   echo 'GOOGLE_API_KEY=AIza...' > .env
   export GOOGLE_API_KEY=AIza...
   ```
3. Install the SDK (already in `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```

The `.env` file and any `*.key` / `secrets.json` are gitignored. Never commit your API key.

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

Gemini 2.0 Flash has a generous free tier (1,500 requests per day, 1M tokens per minute of input). A typical summary call is a few thousand input tokens and under 1024 output tokens, so normal development and demo usage costs nothing. All tests use a mocked Gemini client, so CI does not require an API key and incurs no cost.

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
pip install -r requirements.txt           # Engine only
pip install -r requirements-dev.txt       # Engine + pytest
pip install -r requirements-app.txt       # Engine + Streamlit dashboard
```

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
    summary_model: str = "gemini-2.0-flash-001"
    summary_max_tokens: int = 1024
```

Every field is exposed three ways: as a CLI flag, as a Streamlit slider, and as a dataclass argument when using AuRIS as a library.

## Testing and CI

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

23 pytest tests cover the six risk checks, the report shape, the ML pass, and the AI summary layer:
- `tests/test_audit_risk.py`, 11 tests on the statistical checks.
- `tests/test_ml_anomalies.py`, 7 tests on the Isolation Forest pass.
- `tests/test_summarize.py`, 5 tests on the Gemini summary layer (all mocked, no API calls).

GitHub Actions runs the full test suite against Python 3.10, 3.11, and 3.12 on every push and pull request to `main` and `dev`. See `.github/workflows/ci.yml`.

## Project layout

```
AuRIS/
├── .github/workflows/ci.yml   # Matrix CI: Python 3.10 / 3.11 / 3.12
├── data/transactions.csv      # 10K synthetic rows (from generate_dataset.py)
├── output/                    # Generated reports + plots (gitignored)
├── src/auris/
│   ├── __init__.py
│   ├── __main__.py            # Entry for `python -m auris`
│   ├── audit_risk.py          # Pipeline: 6 checks, 5 plots, CLI
│   └── config.py              # RiskConfig frozen dataclass
├── tests/                     # 18 pytest tests
├── app.py                     # Streamlit dashboard
├── generate_dataset.py        # Synthetic data generator
├── requirements.txt           # Base deps
├── requirements-dev.txt       # Adds pytest
├── requirements-app.txt       # Adds streamlit
└── README.md
```

## Screenshots

- **Sample Input Data**
![image](https://github.com/user-attachments/assets/061d9b0f-93c6-4516-815a-e6e1c05c86e9) <br/>
- **Console Output** <br/>
![image](https://github.com/user-attachments/assets/ac5e0931-a83a-4641-ab9a-450a6f478232)
![image](https://github.com/user-attachments/assets/1ab9b8f4-fe8b-4595-a272-53034c15f0ec) <br/>
- **Output Report Sample**
![Screenshot from 2025-04-13 16-14-07](https://github.com/user-attachments/assets/36d20215-9fca-4af1-987c-b29a2c12b45d)
![Screenshot from 2025-04-13 16-15-40](https://github.com/user-attachments/assets/ef11332b-b319-45ba-9eeb-d0fa844db3e6)
- **Transaction Amount Distribution**
![Screenshot from 2025-04-13 16-08-48](https://github.com/user-attachments/assets/745d0da7-0145-4913-9681-7f7b3e629b93)
- **Vendor Transaction Frequency**
![Screenshot from 2025-04-13 16-09-29](https://github.com/user-attachments/assets/0dead59a-a04e-432f-b60b-4628d19e07e0)
- **Transaction Amounts Over Time**
![Screenshot from 2025-04-13 16-10-07](https://github.com/user-attachments/assets/5c396125-2f33-43c7-b015-1c4762c6bd98)
- **Risk Type Distribution**
![Screenshot from 2025-04-13 16-10-46](https://github.com/user-attachments/assets/57847afc-0287-4771-81c5-084fdbbe7758)
- **Transaction Density by Vendor and Date**
![Screenshot from 2025-04-13 16-11-35](https://github.com/user-attachments/assets/07b0a68c-d301-4e60-b758-fcad7fb1c6fe)
- **Before-and-After Comparison**
![image](https://github.com/user-attachments/assets/8e7cddbe-4d50-4c51-8fe3-a58d1fa5ee6f)
![image](https://github.com/user-attachments/assets/6d5193c7-c2ac-4ce7-ad5d-a7cac976a79e)
![image](https://github.com/user-attachments/assets/8eca3169-c47b-47cb-ba6c-936b1dd21b17)

## Roadmap

AuRIS is being built up in five public, shippable levels. Each level is a separate PR, leaves the existing test suite green, and adds a new capability without rewriting the engine.

1. **AI summary layer.** Shipped. Gemini-powered natural-language risk summary, opt-in via `--summarize`, surfaced as a "Generate AI Summary" button in the Streamlit dashboard. See [AI-Augmented Summaries](#ai-augmented-summaries) above.
2. **Risk scoring engine.** Replace binary flags with a 0-100 numeric risk score per row plus explicit reason codes, weighted across all six checks.
3. **Full-stack conversion.** FastAPI backend wrapping the Python engine, Next.js 15 + TypeScript + shadcn frontend, deployed to Vercel and Railway with a live demo URL.
4. **Persistence, auth, and run history.** Supabase Postgres for multi-tenant run storage, magic-link auth, sharable read-only run URLs, and a side-by-side run comparison view.
5. **ERP integration and production polish.** Pull transactions from Tally, Zoho Books, or ERPNext on a schedule; add Sentry + PostHog observability; ship a public landing page.

## License

This project is open source. See the repository for license details.
