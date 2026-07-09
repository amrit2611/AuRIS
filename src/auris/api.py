"""FastAPI backend wrapping the AuRIS engine.

Same pipeline as the Streamlit dashboard, exposed as REST endpoints so a
Next.js (or any other) frontend can drive it. The engine, scoring layer,
LLM column detection, and AI summary generation are unchanged; this
module is a thin HTTP adaptor.

Endpoints:

- GET  /health              - liveness check, returns pipeline version.
- GET  /config              - default RiskConfig as JSON.
- POST /analyze             - multipart CSV upload; runs the full
                              pipeline (column detection if needed,
                              six checks, scoring) and returns the
                              scored triage queue plus per-check
                              counts and metric totals.
- POST /summarize           - accepts a JSON body with the report and
                              (optional) scored report; returns the
                              Groq/Llama executive summary.

The FastAPI app is exported as `app` so uvicorn can find it:
    uvicorn auris.api:app --host 0.0.0.0 --port 8000

CORS is permissive by default (any origin) so a local Next.js dev
server can talk to a locally-running API. Tighten CORS in production
by setting the AURIS_CORS_ORIGINS env var to a comma-separated list.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any, Optional

# Load .env before importing anything that reads env vars (schema.py and
# summarize.py both check GROQ_API_KEY at call time). Mirrors the pattern
# used by src/auris/__main__.py and app.py so `uvicorn auris.api:app` picks
# up the same .env file the CLI and Streamlit dashboard do.
from dotenv import load_dotenv

load_dotenv()

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auris.audit_risk import (
    check_amount_deviation,
    check_anomalies,
    check_duplicates,
    check_missing,
    check_vendor_frequency,
)
from auris.config import DEFAULT_CONFIG, RiskConfig
from auris.schema import REQUIRED_FIELDS, apply_mapping, detect_columns
from auris.scoring import format_reasons, score_report
from auris.summarize import summarize_risks

logger = logging.getLogger("auris.api")

API_VERSION = "0.1.0"


class RiskConfigModel(BaseModel):
    """Wire-format RiskConfig. Mirrors the dataclass, all fields optional."""

    anomaly_quantile: Optional[float] = None
    vendor_frequency_quantile: Optional[float] = None
    deviation_low_multiplier: Optional[float] = None
    deviation_high_multiplier: Optional[float] = None
    ml_contamination: Optional[float] = None
    duplicate_weight: Optional[float] = None
    anomaly_weight: Optional[float] = None
    deviation_weight: Optional[float] = None
    missing_weight: Optional[float] = None
    frequency_weight: Optional[float] = None
    ml_weight: Optional[float] = None

    def to_dataclass(self) -> RiskConfig:
        """Apply this model's non-None fields on top of DEFAULT_CONFIG."""
        overrides = {k: v for k, v in self.model_dump().items() if v is not None}
        if not overrides:
            return DEFAULT_CONFIG
        return RiskConfig(**{**DEFAULT_CONFIG.__dict__, **overrides})


class HealthResponse(BaseModel):
    status: str = "ok"
    api_version: str = API_VERSION


class PerCheckCounts(BaseModel):
    duplicates: int
    anomalies: int
    missing: int
    high_frequency: int
    amount_deviation: int


class AnalysisMetrics(BaseModel):
    total_transactions: int
    unique_vendors: int
    flagged_pool_unique: int
    priority_queue_count: int = Field(
        description="Rows with risk_score >= 50 (typical triage threshold)."
    )
    total_flagged_amount: float
    top_score: float
    median_score: float


class ColumnMappingInfo(BaseModel):
    used: bool = Field(description="True if LLM column detection ran on this CSV.")
    mapping: dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Detected mapping from AuRIS schema fields to source column names.",
    )


class AnalysisResponse(BaseModel):
    metrics: AnalysisMetrics
    per_check_counts: PerCheckCounts
    column_mapping: ColumnMappingInfo
    scored_rows: list[dict[str, Any]] = Field(
        description="Scored triage queue, one row per invoice_id, sorted by risk_score desc.",
    )
    report_rows: list[dict[str, Any]] = Field(
        description="Raw check-hit report before scoring (one row per (row, check) pair).",
    )


class SummarizeRequest(BaseModel):
    report_rows: list[dict[str, Any]] = Field(
        description="The raw check-hit report from /analyze.",
    )
    scored_rows: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Optional scored triage queue from /analyze. When provided, "
        "the AI summary includes a Top rows by risk score section.",
    )
    config: Optional[RiskConfigModel] = None


class SummarizeResponse(BaseModel):
    summary_markdown: str


def _serialise_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe dicts."""
    if df is None or df.empty:
        return []
    # `reasons` may contain lists; leave as-is for JSON, but stringify for CSV export.
    return df.replace({pd.NA: None}).to_dict(orient="records")


def create_app() -> FastAPI:
    """Build the FastAPI app. Factory so tests can rebuild per test if needed."""
    app = FastAPI(
        title="AuRIS API",
        description=(
            "Audit-risk pipeline as REST. Upload a CSV; get six statistical "
            "risk checks, a scored triage queue, and optionally an "
            "LLM-generated executive summary."
        ),
        version=API_VERSION,
    )

    origins_env = os.environ.get("AURIS_CORS_ORIGINS", "*")
    origins = ["*"] if origins_env == "*" else [o.strip() for o in origins_env.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/config", response_model=dict[str, Any])
    def get_config() -> dict[str, Any]:
        """Return the default RiskConfig as a JSON dict."""
        return DEFAULT_CONFIG.__dict__.copy()

    @app.post("/analyze", response_model=AnalysisResponse)
    async def analyze(
        file: UploadFile = File(..., description="Transactions CSV."),
    ) -> AnalysisResponse:
        """Run the full pipeline on an uploaded CSV.

        - If the CSV already has AuRIS's four required columns
          (vendor, amount, date, invoice_id), the pipeline runs as-is.
        - Otherwise, the LLM column detector maps arbitrary column
          names into AuRIS's schema. Requires GROQ_API_KEY.
        """
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(400, "Only CSV files are supported.")

        raw = await file.read()
        try:
            data = pd.read_csv(io.BytesIO(raw), low_memory=False)
        except Exception as exc:
            raise HTTPException(400, f"Could not parse CSV: {exc}")

        if data.empty:
            raise HTTPException(400, "CSV is empty.")

        config = DEFAULT_CONFIG

        # Column detection: only when the schema is not already present.
        already_mapped = set(REQUIRED_FIELDS).issubset(data.columns)
        mapping_info = ColumnMappingInfo(used=False)
        if not already_mapped:
            try:
                detected = detect_columns(data, config)
                data = apply_mapping(data, detected)
                mapping_info = ColumnMappingInfo(used=True, mapping=detected)
            except Exception as exc:
                logger.error("column detection failed: %s", exc)
                raise HTTPException(
                    422,
                    f"Column detection failed and CSV does not match AuRIS's default "
                    f"schema. Provide vendor/amount/date/invoice_id columns, or ensure "
                    f"GROQ_API_KEY is set. Detail: {exc}",
                )

        # Missing required columns even after mapping is a caller bug.
        missing_required = [c for c in REQUIRED_FIELDS if c not in data.columns]
        if missing_required:
            raise HTTPException(
                422,
                f"After column detection, still missing required columns: {missing_required}.",
            )

        # Run all five statistical checks.
        duplicates = check_duplicates(data)
        anomalies = check_anomalies(data, config)
        missing = check_missing(data)
        frequent = check_vendor_frequency(data, config)
        deviations = check_amount_deviation(data, config)

        report = pd.concat(
            [duplicates, anomalies, missing, frequent, deviations],
            ignore_index=True,
        )
        scored = score_report(report, config)

        # Build metrics.
        total_flagged_amount = (
            float(report["amount"].dropna().sum()) if not report.empty else 0.0
        )
        top_score = float(scored["risk_score"].max()) if not scored.empty else 0.0
        median_score = float(scored["risk_score"].median()) if not scored.empty else 0.0
        priority_count = int((scored["risk_score"] >= 50).sum()) if not scored.empty else 0

        # Serialise the reasons column (lists) as human-readable strings for the
        # JSON payload so JS callers don't have to concat arrays for display.
        scored_display = scored.copy()
        if not scored_display.empty and "reasons" in scored_display.columns:
            scored_display["reasons"] = scored_display["reasons"].apply(format_reasons)

        return AnalysisResponse(
            metrics=AnalysisMetrics(
                total_transactions=int(len(data)),
                unique_vendors=int(data["vendor"].nunique()),
                flagged_pool_unique=int(len(scored)),
                priority_queue_count=priority_count,
                total_flagged_amount=total_flagged_amount,
                top_score=top_score,
                median_score=median_score,
            ),
            per_check_counts=PerCheckCounts(
                duplicates=int(len(duplicates)),
                anomalies=int(len(anomalies)),
                missing=int(len(missing)),
                high_frequency=int(len(frequent)),
                amount_deviation=int(len(deviations)),
            ),
            column_mapping=mapping_info,
            scored_rows=_serialise_rows(scored_display),
            report_rows=_serialise_rows(report),
        )

    @app.post("/summarize", response_model=SummarizeResponse)
    def summarize(request: SummarizeRequest) -> SummarizeResponse:
        """Generate a Markdown executive summary via Groq.

        Accepts the raw report from /analyze plus (optionally) the scored
        triage queue. When the scored view is provided, the summary
        prompt includes a Top rows by risk score section for sharper
        Priority Actions.
        """
        if not request.report_rows:
            raise HTTPException(400, "report_rows is required and cannot be empty.")

        config = (
            request.config.to_dataclass() if request.config is not None else DEFAULT_CONFIG
        )

        report_df = pd.DataFrame(request.report_rows)
        scored_df: Optional[pd.DataFrame] = None
        if request.scored_rows:
            scored_df = pd.DataFrame(request.scored_rows)
            # Recover the reasons column: /analyze serialises it as a string
            # ("A; B; C") so we split it back into a list for the prompt.
            if "reasons" in scored_df.columns:
                scored_df["reasons"] = scored_df["reasons"].apply(
                    lambda v: [s.strip() for s in v.split(";")] if isinstance(v, str) else v
                )

        try:
            markdown = summarize_risks(report_df, config, scored=scored_df)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return SummarizeResponse(summary_markdown=markdown)

    return app


app = create_app()
