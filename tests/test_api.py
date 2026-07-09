"""Tests for the FastAPI backend (src/auris/api.py).

FastAPI's TestClient drives the endpoints. The LLM-touching endpoints
(schema.detect_columns and summarize.summarize_risks) are mocked at
their call sites in the api module so no real API calls happen in CI.
"""
from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from auris.api import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def synthetic_csv() -> bytes:
    """A tiny CSV already in AuRIS's schema, so LLM detection is skipped."""
    rows = [
        # duplicates on same vendor/amount/date
        {"invoice_id": 1, "vendor": "A", "amount": 100.0, "date": "2025-01-01"},
        {"invoice_id": 2, "vendor": "A", "amount": 100.0, "date": "2025-01-01"},
        # one big outlier for anomaly
        {"invoice_id": 3, "vendor": "B", "amount": 9999.0, "date": "2025-01-02"},
        # a mix of small transactions so scoring has variety
        {"invoice_id": 4, "vendor": "C", "amount": 50.0, "date": "2025-01-03"},
        {"invoice_id": 5, "vendor": "C", "amount": 55.0, "date": "2025-01-04"},
        {"invoice_id": 6, "vendor": "D", "amount": 60.0, "date": "2025-01-05"},
    ]
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "api_version" in body


# ---------------------------------------------------------------------------
# /config
# ---------------------------------------------------------------------------

def test_config_returns_default_riskconfig_fields(client: TestClient) -> None:
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    # Must include the AuRIS knobs a caller would want to display.
    for field in [
        "anomaly_quantile", "vendor_frequency_quantile",
        "deviation_low_multiplier", "deviation_high_multiplier",
        "ml_contamination",
        "duplicate_weight", "anomaly_weight", "deviation_weight",
        "missing_weight", "frequency_weight", "ml_weight",
        "summary_model", "summary_max_tokens",
    ]:
        assert field in body, f"missing {field} in /config response"


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------

def test_analyze_rejects_non_csv(client: TestClient) -> None:
    r = client.post(
        "/analyze",
        files={"file": ("data.txt", b"not,a,csv", "text/plain")},
    )
    assert r.status_code == 400
    assert "CSV" in r.json()["detail"]


def test_analyze_rejects_empty_csv(client: TestClient) -> None:
    # A CSV file with only whitespace parses to an empty DataFrame.
    r = client.post(
        "/analyze",
        files={"file": ("empty.csv", b"\n", "text/csv")},
    )
    assert r.status_code == 400


def test_analyze_runs_pipeline_on_schema_matching_csv(
    client: TestClient, synthetic_csv: bytes
) -> None:
    """When the CSV already has AuRIS's schema, no LLM call is made."""
    r = client.post(
        "/analyze",
        files={"file": ("transactions.csv", synthetic_csv, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Shape assertions
    assert body["column_mapping"]["used"] is False
    assert body["metrics"]["total_transactions"] == 6
    assert body["metrics"]["unique_vendors"] == 4  # A, B, C, D

    # The synthetic data was designed to fire duplicates on rows 1-2 and
    # anomaly on row 3.
    assert body["per_check_counts"]["duplicates"] == 2
    assert body["per_check_counts"]["anomalies"] >= 1

    # Scored triage queue exists and is sorted by score descending.
    scored = body["scored_rows"]
    assert isinstance(scored, list)
    if len(scored) > 1:
        scores = [row["risk_score"] for row in scored]
        assert scores == sorted(scores, reverse=True)

    # Each scored row has the expected columns.
    if scored:
        assert "risk_score" in scored[0]
        assert "reasons" in scored[0]
        assert isinstance(scored[0]["reasons"], str)  # serialised for display


def test_analyze_calls_llm_column_detection_when_schema_absent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the CSV does not match AuRIS's schema, detect_columns is invoked."""
    # A CSV using different column names.
    df = pd.DataFrame([
        {"awd_id": 1, "recipient": "A", "usd": 100.0, "action_date": "2025-01-01"},
        {"awd_id": 2, "recipient": "A", "usd": 100.0, "action_date": "2025-01-01"},
        {"awd_id": 3, "recipient": "B", "usd": 9999.0, "action_date": "2025-01-02"},
    ])
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    fake_mapping = {
        "vendor": "recipient",
        "amount": "usd",
        "date": "action_date",
        "invoice_id": "awd_id",
    }
    with patch("auris.api.detect_columns", return_value=fake_mapping) as mock_detect:
        r = client.post(
            "/analyze",
            files={"file": ("odd_columns.csv", csv_bytes, "text/csv")},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["column_mapping"]["used"] is True
    assert body["column_mapping"]["mapping"] == fake_mapping
    mock_detect.assert_called_once()


def test_analyze_returns_422_when_column_detection_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """detect_columns raising RuntimeError bubbles up as 422."""
    df = pd.DataFrame([{"a": 1, "b": 2, "c": 3, "d": 4}])
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    with patch(
        "auris.api.detect_columns",
        side_effect=RuntimeError("GROQ_API_KEY missing"),
    ):
        r = client.post(
            "/analyze",
            files={"file": ("no_key.csv", csv_bytes, "text/csv")},
        )
    assert r.status_code == 422
    assert "GROQ_API_KEY" in r.json()["detail"]


# ---------------------------------------------------------------------------
# /summarize
# ---------------------------------------------------------------------------

def test_summarize_rejects_empty_report_rows(client: TestClient) -> None:
    r = client.post("/summarize", json={"report_rows": []})
    assert r.status_code == 400


def test_summarize_delegates_to_summarize_risks(client: TestClient) -> None:
    """Summarize should hand off to summarize_risks and return its markdown."""
    with patch(
        "auris.api.summarize_risks",
        return_value="# AuRIS Risk Summary\n\nMocked body.",
    ) as mock_summarize:
        r = client.post(
            "/summarize",
            json={
                "report_rows": [
                    {"invoice_id": 1, "vendor": "X", "amount": 100.0,
                     "date": "2025-01-01", "risk_type": "Duplicate"},
                ],
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary_markdown"].startswith("# AuRIS Risk Summary")
    mock_summarize.assert_called_once()
    # Confirm the config default was applied (positional arg 2) and no scored
    # was passed (kwarg scored=None).
    _, kwargs = mock_summarize.call_args
    assert kwargs["scored"] is None


def test_summarize_passes_scored_when_provided(client: TestClient) -> None:
    """When scored_rows is in the request body, it must be forwarded to summarize_risks."""
    with patch(
        "auris.api.summarize_risks",
        return_value="# AuRIS Risk Summary\n\nWith scored.",
    ) as mock_summarize:
        r = client.post(
            "/summarize",
            json={
                "report_rows": [
                    {"invoice_id": 1, "vendor": "X", "amount": 100.0,
                     "date": "2025-01-01", "risk_type": "Duplicate"},
                ],
                "scored_rows": [
                    {"invoice_id": 1, "vendor": "X", "amount": 100.0,
                     "date": "2025-01-01", "risk_score": 25.0,
                     "reasons": "Duplicate"},
                ],
            },
        )
    assert r.status_code == 200, r.text
    _, kwargs = mock_summarize.call_args
    assert kwargs["scored"] is not None
    # reasons should have been split back into a list on the way in.
    assert list(kwargs["scored"]["reasons"].iloc[0]) == ["Duplicate"]


def test_summarize_returns_503_when_api_key_missing(client: TestClient) -> None:
    """A RuntimeError from summarize_risks (missing key) maps to 503."""
    with patch(
        "auris.api.summarize_risks",
        side_effect=RuntimeError("GROQ_API_KEY environment variable is required"),
    ):
        r = client.post(
            "/summarize",
            json={
                "report_rows": [
                    {"invoice_id": 1, "vendor": "X", "amount": 100.0,
                     "date": "2025-01-01", "risk_type": "Duplicate"},
                ],
            },
        )
    assert r.status_code == 503
    assert "GROQ_API_KEY" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Config overrides
# ---------------------------------------------------------------------------

def test_config_model_applies_overrides_on_top_of_defaults() -> None:
    """RiskConfigModel.to_dataclass merges overrides with DEFAULT_CONFIG."""
    from auris.api import RiskConfigModel
    from auris.config import DEFAULT_CONFIG

    model = RiskConfigModel(anomaly_quantile=0.995, duplicate_weight=40.0)
    result = model.to_dataclass()
    assert result.anomaly_quantile == 0.995
    assert result.duplicate_weight == 40.0
    # Untouched fields keep the default value.
    assert result.vendor_frequency_quantile == DEFAULT_CONFIG.vendor_frequency_quantile
    assert result.summary_model == DEFAULT_CONFIG.summary_model


def test_config_model_with_no_overrides_returns_default() -> None:
    """An empty RiskConfigModel returns the DEFAULT_CONFIG instance."""
    from auris.api import RiskConfigModel
    from auris.config import DEFAULT_CONFIG

    model = RiskConfigModel()
    assert model.to_dataclass() is DEFAULT_CONFIG
