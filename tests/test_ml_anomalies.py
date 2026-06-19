"""Behavior tests for the Isolation Forest ML anomaly check."""
import pandas as pd
import pytest

from auris.audit_risk import check_ml_anomalies, generate_report
from auris.config import RiskConfig


@pytest.fixture
def ml_sample() -> pd.DataFrame:
    """50 normal rows around amount=100 plus 3 obvious multivariate outliers.

    Rows 1-50 are clustered tightly. The last three (51-53) have amounts
    several orders of magnitude larger than the cluster, so a seeded
    Isolation Forest should flag them with high confidence.
    """
    normal = [
        {"invoice_id": i, "vendor": ["A", "B", "C"][i % 3], "amount": 100.0 + (i % 10),
         "date": f"2025-01-{(i % 28) + 1:02d}"}
        for i in range(1, 51)
    ]
    outliers = [
        {"invoice_id": 51, "vendor": "A", "amount": 99999.0, "date": "2025-01-15"},
        {"invoice_id": 52, "vendor": "B", "amount": 50000.0, "date": "2025-01-16"},
        {"invoice_id": 53, "vendor": "C", "amount": 75000.0, "date": "2025-01-17"},
    ]
    return pd.DataFrame(normal + outliers)


def test_check_ml_anomalies_flags_outliers(ml_sample):
    """Seeded Isolation Forest should flag the planted outliers."""
    result = check_ml_anomalies(ml_sample)
    assert not result.empty
    assert (result["risk_type"] == "ML Anomaly").all()
    flagged_ids = set(result["invoice_id"])
    planted_outliers = {51, 52, 53}
    assert planted_outliers.issubset(flagged_ids), (
        f"expected planted outliers {planted_outliers} flagged, got {flagged_ids}"
    )


def test_check_ml_anomalies_is_deterministic(ml_sample):
    """Two runs with the same random_state produce the same flagged ids."""
    first = check_ml_anomalies(ml_sample)
    second = check_ml_anomalies(ml_sample)
    assert set(first["invoice_id"]) == set(second["invoice_id"])


def test_check_ml_anomalies_respects_contamination(ml_sample):
    """Higher contamination flags at least as many rows as lower."""
    sparse = check_ml_anomalies(ml_sample, RiskConfig(ml_contamination=0.02))
    dense = check_ml_anomalies(ml_sample, RiskConfig(ml_contamination=0.20))
    assert len(dense) >= len(sparse)


def test_check_ml_anomalies_missing_columns_returns_empty():
    df = pd.DataFrame([{"vendor": "A", "date": "2025-01-01"}])
    assert check_ml_anomalies(df).empty


def test_check_ml_anomalies_too_few_rows_returns_empty():
    df = pd.DataFrame([
        {"invoice_id": i, "vendor": "A", "amount": 100.0, "date": "2025-01-01"}
        for i in range(5)
    ])
    assert check_ml_anomalies(df).empty


def test_generate_report_includes_ml_anomalies(tmp_path, ml_sample):
    """generate_report concatenates ml_anomalies when provided."""
    empty = pd.DataFrame()
    ml = check_ml_anomalies(ml_sample)
    report = generate_report(empty, empty, empty, empty, empty, tmp_path, ml_anomalies=ml)
    assert (tmp_path / "risks_report.csv").exists()
    assert "ML Anomaly" in set(report["risk_type"].unique())


def test_generate_report_backward_compatible_without_ml(tmp_path):
    """Original five-arg signature still works without ml_anomalies."""
    empty = pd.DataFrame()
    one_row = pd.DataFrame([{"invoice_id": 1, "vendor": "A", "amount": 100,
                             "date": "2025-01-01", "risk_type": "Duplicate"}])
    report = generate_report(one_row, empty, empty, empty, empty, tmp_path)
    assert set(report["risk_type"].unique()) == {"Duplicate"}
