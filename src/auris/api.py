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
import secrets
import time
from typing import Any, Optional

# Load .env before importing anything that reads env vars (schema.py and
# summarize.py both check GROQ_API_KEY at call time). Use usecwd=True so
# find_dotenv walks up from the process CWD (repo root when uvicorn is
# launched from there), not from this module's install location. Without
# usecwd, a snapshot install under site-packages would make find_dotenv
# search there instead and miss the repo's .env.
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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

# uvicorn only configures its own uvicorn.* loggers, so app logs from the
# `auris` hierarchy go nowhere by default. Attach a StreamHandler to the
# `auris` root so every log line from api.py, schema.py, summarize.py etc.
# actually reaches the container's stderr and shows up in Render / Docker
# logs. Level is controlled by AURIS_LOG_LEVEL (default INFO); flip to
# DEBUG on Render to reveal /health probe traces without a code change.
_auris_root = logging.getLogger("auris")
if not _auris_root.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    _auris_root.addHandler(_h)
    _level_name = os.environ.get("AURIS_LOG_LEVEL", "INFO").upper()
    _auris_root.setLevel(getattr(logging, _level_name, logging.INFO))
    # Don't double-emit if some caller also configured the root logger.
    _auris_root.propagate = False

API_VERSION = "0.1.0"


class _HealthAccessFilter(logging.Filter):
    """Drop uvicorn access-log lines for /health polls.

    Render and most PaaS hosts hit /health every few seconds; if those
    lines survive to the log stream they dominate everything else. Our
    own middleware (below) already skips /health, so this filter only
    needs to hide uvicorn's default access log for the same path.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        # UptimeRobot (and many other external monitors) default to
        # HEAD requests for health probes; internal Render checks use
        # GET. Filter both so keep-alive traffic never survives to the
        # log stream regardless of the monitor's implementation.
        return '"GET /health' not in msg and '"HEAD /health' not in msg


# Registered at import time (not inside create_app) so the filter is in
# place before the first request lands, and so tests that build a fresh
# app via create_app() don't stack duplicate filter instances on each call.
_uvicorn_access_logger = logging.getLogger("uvicorn.access")
if not any(isinstance(f, _HealthAccessFilter) for f in _uvicorn_access_logger.filters):
    _uvicorn_access_logger.addFilter(_HealthAccessFilter())


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

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        """Per-request log line: INFO for regular endpoints, DEBUG for /health.

        No request is silent: every one gets a start + done trace with an
        8-char request_id, method, path, status, and latency. /health is
        emitted at DEBUG so it stays out of the default INFO stream (where
        Render's 5-second internal probe + UptimeRobot's 5-minute external
        probe would otherwise drown real user traffic) but is still
        recoverable when investigating - flip uvicorn to `--log-level
        debug` and every probe is visible.

        The request_id is attached to request.state so endpoint handlers
        can tag their own business-level logs (row counts, overrides,
        mapping, etc.) with the same id and be correlated.
        """
        path = request.url.path
        # /health polls are high-volume routine traffic; log them at DEBUG
        # so the INFO stream stays readable. Everything else is INFO.
        log = logger.debug if path == "/health" else logger.info

        request_id = secrets.token_hex(4)
        request.state.request_id = request_id
        start = time.perf_counter()
        client = request.client.host if request.client else "?"
        log(
            "req=%s %s %s start client=%s",
            request_id, request.method, path, client,
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            # Uncaught exceptions always ERROR regardless of endpoint;
            # a /health crash is exactly the thing we want to see in
            # the default log stream.
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(
                "req=%s %s %s crashed exc=%s elapsed_ms=%.1f",
                request_id, request.method, path, type(exc).__name__, elapsed,
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000
        log(
            "req=%s %s %s done status=%d elapsed_ms=%.1f",
            request_id, request.method, path, response.status_code, elapsed,
        )
        return response

    # Upload size cap. Free-tier PaaS instances (Render Free = 512MB RAM)
    # OOM-crash when pandas materialises a large CSV, so reject oversize
    # uploads early with a friendly 413 instead of taking the service down.
    # Configurable via AURIS_MAX_UPLOAD_MB env var so heavier deployments
    # can lift it. Default 10 MB comfortably handles ~50k-row transaction
    # CSVs with the columns AuRIS actually reads.
    try:
        max_upload_mb = float(os.environ.get("AURIS_MAX_UPLOAD_MB", "10"))
    except ValueError:
        max_upload_mb = 10.0
    max_upload_bytes = int(max_upload_mb * 1024 * 1024)

    @app.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
    def health() -> HealthResponse:
        """Liveness probe. Answers both GET and HEAD so external monitors
        (UptimeRobot, Better Stack, etc.) that default to HEAD do not
        get a 405; Starlette handles the body-stripping for HEAD."""
        return HealthResponse()

    @app.get("/config", response_model=dict[str, Any])
    def get_config() -> dict[str, Any]:
        """Return the default RiskConfig as a JSON dict."""
        return DEFAULT_CONFIG.__dict__.copy()

    @app.post("/analyze", response_model=AnalysisResponse)
    async def analyze(
        request: Request,
        file: UploadFile = File(..., description="Transactions CSV."),
        config: Optional[str] = Form(
            None,
            description=(
                "Optional JSON-encoded RiskConfigModel overrides. Any subset "
                "of the RiskConfigModel fields; missing fields fall back to "
                "DEFAULT_CONFIG. Sent as a multipart form field so it lives "
                "alongside the file upload without a second request."
            ),
        ),
    ) -> AnalysisResponse:
        """Run the full pipeline on an uploaded CSV.

        - If the CSV already has AuRIS's four required columns
          (vendor, amount, date, invoice_id), the pipeline runs as-is.
        - Otherwise, the LLM column detector maps arbitrary column
          names into AuRIS's schema. Requires GROQ_API_KEY.
        - Optional `config` form field lets a caller override any
          RiskConfigModel field (thresholds, ML params, scoring weights).
        """
        rid = getattr(request.state, "request_id", "?")

        if not file.filename or not file.filename.lower().endswith(".csv"):
            logger.warning(
                "req=%s analyze rejected non_csv filename=%r content_type=%s",
                rid, file.filename, file.content_type,
            )
            raise HTTPException(400, "Only CSV files are supported.")

        # Fast path: reject via Content-Length header before reading any
        # bytes. Cheap and protects the process from a malicious client
        # streaming gigabytes.
        content_length = file.size
        if content_length is not None and content_length > max_upload_bytes:
            raise HTTPException(
                413,
                f"CSV is {content_length / 1024 / 1024:.1f} MB, over the "
                f"{max_upload_mb:.0f} MB demo cap. Try a smaller file, or run "
                f"AuRIS locally (`python -m auris -i <path>`) for no cap.",
            )

        raw = await file.read()
        logger.info(
            "req=%s analyze recv filename=%r bytes=%d has_config=%s",
            rid, file.filename, len(raw), config is not None,
        )

        # Defense in depth: content-length can be absent or wrong; enforce
        # the same cap on actual bytes read.
        if len(raw) > max_upload_bytes:
            raise HTTPException(
                413,
                f"CSV is {len(raw) / 1024 / 1024:.1f} MB, over the "
                f"{max_upload_mb:.0f} MB demo cap. Try a smaller file, or run "
                f"AuRIS locally (`python -m auris -i <path>`) for no cap.",
            )

        try:
            data = pd.read_csv(io.BytesIO(raw), low_memory=False)
        except Exception as exc:
            logger.warning(
                "req=%s analyze rejected parse_error filename=%r exc=%s",
                rid, file.filename, exc,
            )
            raise HTTPException(400, f"Could not parse CSV: {exc}")

        if data.empty:
            logger.warning(
                "req=%s analyze rejected empty_csv filename=%r",
                rid, file.filename,
            )
            raise HTTPException(400, "CSV is empty.")

        # Resolve the RiskConfig for this request: caller overrides on top of
        # DEFAULT_CONFIG, or DEFAULT_CONFIG if no `config` form field was sent.
        # Reused later for detect_columns, all five checks, scoring, and any
        # LLM prompt that reads config.summary_model.
        if config is not None:
            try:
                overrides = RiskConfigModel.model_validate_json(config)
            except Exception as exc:
                logger.warning(
                    "req=%s analyze rejected bad_config_json exc=%s",
                    rid, exc,
                )
                raise HTTPException(
                    400,
                    f"Invalid `config` payload; expected JSON matching RiskConfigModel: {exc}",
                )
            risk_config = overrides.to_dataclass()
            override_fields = list(overrides.model_dump(exclude_none=True).keys())
            logger.info(
                "req=%s analyze config_override fields=%s",
                rid, override_fields,
            )
        else:
            risk_config = DEFAULT_CONFIG

        logger.info(
            "req=%s analyze parsed rows=%d columns=%d",
            rid, len(data), len(data.columns),
        )

        # Column detection: only when the schema is not already present.
        already_mapped = set(REQUIRED_FIELDS).issubset(data.columns)
        mapping_info = ColumnMappingInfo(used=False)
        if already_mapped:
            logger.info("req=%s analyze schema_native", rid)
        else:
            logger.info(
                "req=%s analyze llm_column_detect model=%s columns=%d",
                rid, risk_config.summary_model, len(data.columns),
            )
            try:
                detected = detect_columns(data, risk_config)
                data = apply_mapping(data, detected)
                mapping_info = ColumnMappingInfo(used=True, mapping=detected)
                logger.info(
                    "req=%s analyze llm_column_detect ok mapping=%s",
                    rid, detected,
                )
            except Exception as exc:
                logger.error(
                    "req=%s analyze llm_column_detect failed exc=%s",
                    rid, exc,
                )
                raise HTTPException(
                    422,
                    f"Column detection failed and CSV does not match AuRIS's default "
                    f"schema. Provide vendor/amount/date/invoice_id columns, or ensure "
                    f"GROQ_API_KEY is set. Detail: {exc}",
                )

        # Missing required columns even after mapping is a caller bug.
        missing_required = [c for c in REQUIRED_FIELDS if c not in data.columns]
        if missing_required:
            logger.warning(
                "req=%s analyze rejected missing_required missing=%s",
                rid, missing_required,
            )
            raise HTTPException(
                422,
                f"After column detection, still missing required columns: {missing_required}.",
            )

        # Run all five statistical checks.
        duplicates = check_duplicates(data)
        anomalies = check_anomalies(data, risk_config)
        missing = check_missing(data)
        frequent = check_vendor_frequency(data, risk_config)
        deviations = check_amount_deviation(data, risk_config)

        report = pd.concat(
            [duplicates, anomalies, missing, frequent, deviations],
            ignore_index=True,
        )
        scored = score_report(report, risk_config)

        # Build metrics.
        total_flagged_amount = (
            float(report["amount"].dropna().sum()) if not report.empty else 0.0
        )
        top_score = float(scored["risk_score"].max()) if not scored.empty else 0.0
        median_score = float(scored["risk_score"].median()) if not scored.empty else 0.0
        priority_count = int((scored["risk_score"] >= 50).sum()) if not scored.empty else 0

        logger.info(
            "req=%s analyze pipeline_done rows=%d flagged=%d priority=%d top=%.1f "
            "duplicates=%d anomalies=%d missing=%d frequency=%d deviation=%d",
            rid, len(data), len(scored), priority_count, top_score,
            len(duplicates), len(anomalies), len(missing),
            len(frequent), len(deviations),
        )

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
    def summarize(
        http_request: Request, payload: SummarizeRequest
    ) -> SummarizeResponse:
        """Generate a Markdown executive summary via Groq.

        Accepts the raw report from /analyze plus (optionally) the scored
        triage queue. When the scored view is provided, the summary
        prompt includes a Top rows by risk score section for sharper
        Priority Actions.
        """
        rid = getattr(http_request.state, "request_id", "?")

        if not payload.report_rows:
            logger.warning("req=%s summarize rejected empty_report", rid)
            raise HTTPException(400, "report_rows is required and cannot be empty.")

        config = (
            payload.config.to_dataclass() if payload.config is not None else DEFAULT_CONFIG
        )

        report_df = pd.DataFrame(payload.report_rows)
        scored_df: Optional[pd.DataFrame] = None
        if payload.scored_rows:
            scored_df = pd.DataFrame(payload.scored_rows)
            # Recover the reasons column: /analyze serialises it as a string
            # ("A; B; C") so we split it back into a list for the prompt.
            if "reasons" in scored_df.columns:
                scored_df["reasons"] = scored_df["reasons"].apply(
                    lambda v: [s.strip() for s in v.split(";")] if isinstance(v, str) else v
                )

        logger.info(
            "req=%s summarize start report_rows=%d scored_rows=%d model=%s has_override=%s",
            rid, len(payload.report_rows),
            len(payload.scored_rows) if payload.scored_rows else 0,
            config.summary_model, payload.config is not None,
        )

        llm_start = time.perf_counter()
        try:
            markdown = summarize_risks(report_df, config, scored=scored_df)
        except RuntimeError as exc:
            logger.error("req=%s summarize llm_error exc=%s", rid, exc)
            raise HTTPException(503, str(exc))
        except ValueError as exc:
            logger.warning("req=%s summarize input_error exc=%s", rid, exc)
            raise HTTPException(400, str(exc))
        llm_elapsed = (time.perf_counter() - llm_start) * 1000
        logger.info(
            "req=%s summarize done markdown_chars=%d llm_ms=%.1f",
            rid, len(markdown), llm_elapsed,
        )
        return SummarizeResponse(summary_markdown=markdown)

    return app


app = create_app()
