"""Tests for the Level 2 risk-scoring engine."""
import pandas as pd
import pytest

from auris.config import RiskConfig
from auris.scoring import (
    _MAX_SCORE,
    _weight_for,
    format_reasons,
    score_report,
    top_n_by_score,
)


@pytest.fixture
def overlapping_report() -> pd.DataFrame:
    """A report where two invoice_ids fire multiple checks and one fires just once."""
    return pd.DataFrame([
        # invoice 100: flagged by Duplicate + Anomaly + ML Anomaly (25 + 20 + 20 = 65)
        {"invoice_id": 100, "vendor": "A", "amount": 5000.0, "date": "2025-01-01", "risk_type": "Duplicate"},
        {"invoice_id": 100, "vendor": "A", "amount": 5000.0, "date": "2025-01-01", "risk_type": "Anomaly"},
        {"invoice_id": 100, "vendor": "A", "amount": 5000.0, "date": "2025-01-01", "risk_type": "ML Anomaly"},
        # invoice 200: flagged by Missing Data only (10)
        {"invoice_id": 200, "vendor": "B", "amount": None, "date": "2025-01-02", "risk_type": "Missing Data"},
        # invoice 300: flagged by every check (25 + 20 + 15 + 10 + 10 + 20 = 100)
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "Duplicate"},
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "Anomaly"},
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "Amount Deviation"},
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "Missing Data"},
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "High Frequency"},
        {"invoice_id": 300, "vendor": "C", "amount": 9999.0, "date": "2025-01-03", "risk_type": "ML Anomaly"},
    ])


def test_score_report_deduplicates_by_invoice_id(overlapping_report: pd.DataFrame) -> None:
    """Overlapping check-hits on the same invoice collapse into one scored row."""
    scored = score_report(overlapping_report, RiskConfig())
    assert set(scored["invoice_id"]) == {100, 200, 300}
    assert len(scored) == 3


def test_score_report_sums_weights_and_lists_reasons(overlapping_report: pd.DataFrame) -> None:
    """A row's score is the sum of its contributing check weights; reasons list them."""
    scored = score_report(overlapping_report, RiskConfig()).set_index("invoice_id")

    assert scored.loc[100, "risk_score"] == pytest.approx(65.0)  # 25 + 20 + 20
    assert set(scored.loc[100, "reasons"]) == {"Duplicate", "Anomaly", "ML Anomaly"}

    assert scored.loc[200, "risk_score"] == pytest.approx(10.0)
    assert scored.loc[200, "reasons"] == ["Missing Data"]

    assert scored.loc[300, "risk_score"] == pytest.approx(100.0)  # sum = 100
    assert len(scored.loc[300, "reasons"]) == 6


def test_score_report_caps_score_at_100(overlapping_report: pd.DataFrame) -> None:
    """With inflated weights, a row's score still tops out at 100."""
    config = RiskConfig(
        duplicate_weight=100, anomaly_weight=100, deviation_weight=100,
        missing_weight=100, frequency_weight=100, ml_weight=100,
    )
    scored = score_report(overlapping_report, config).set_index("invoice_id")
    assert scored["risk_score"].max() <= _MAX_SCORE
    # invoice 300 fires all 6 checks, would sum to 600 without the cap.
    assert scored.loc[300, "risk_score"] == pytest.approx(_MAX_SCORE)


def test_score_report_sorts_descending_by_score(overlapping_report: pd.DataFrame) -> None:
    """Output is a ready-made triage queue: highest score first."""
    scored = score_report(overlapping_report, RiskConfig())
    scores = scored["risk_score"].tolist()
    assert scores == sorted(scores, reverse=True)
    assert scored.iloc[0]["invoice_id"] == 300  # 100 wins
    assert scored.iloc[-1]["invoice_id"] == 200  # 10 loses


def test_score_report_respects_custom_weights() -> None:
    """Overriding weights on RiskConfig changes the resulting scores."""
    report = pd.DataFrame([
        {"invoice_id": 1, "vendor": "X", "amount": 100.0, "date": "2025-01-01", "risk_type": "Duplicate"},
    ])
    weak_dupes = RiskConfig(duplicate_weight=5.0)
    strong_dupes = RiskConfig(duplicate_weight=80.0)
    assert score_report(report, weak_dupes).iloc[0]["risk_score"] == pytest.approx(5.0)
    assert score_report(report, strong_dupes).iloc[0]["risk_score"] == pytest.approx(80.0)


def test_score_report_handles_empty_input() -> None:
    """An empty report round-trips cleanly with the new columns present."""
    empty = pd.DataFrame(columns=["invoice_id", "vendor", "amount", "date", "risk_type"])
    result = score_report(empty, RiskConfig())
    assert "risk_score" in result.columns
    assert "reasons" in result.columns
    assert result.empty


def test_score_report_warns_on_unknown_risk_type(caplog: pytest.LogCaptureFixture) -> None:
    """A risk_type not in the weight map contributes 0 with a warning."""
    report = pd.DataFrame([
        {"invoice_id": 1, "vendor": "X", "amount": 100.0, "date": "2025-01-01", "risk_type": "Mystery Type"},
    ])
    caplog.set_level("WARNING", logger="auris")
    result = score_report(report, RiskConfig())
    assert result.iloc[0]["risk_score"] == pytest.approx(0.0)
    assert any("Mystery Type" in rec.message for rec in caplog.records)


def test_score_report_falls_back_when_no_invoice_id(overlapping_report: pd.DataFrame) -> None:
    """Missing invoice_id column: each check-hit becomes its own scored row."""
    without_id = overlapping_report.drop(columns=["invoice_id"])
    scored = score_report(without_id, RiskConfig())
    assert len(scored) == len(without_id)
    assert "risk_score" in scored.columns
    # First row should be one of the high-weight checks (Duplicate, Anomaly, or ML).
    assert scored.iloc[0]["risk_score"] >= 20.0


def test_top_n_by_score_returns_head(overlapping_report: pd.DataFrame) -> None:
    """top_n_by_score returns the first N rows of an already-sorted DataFrame."""
    scored = score_report(overlapping_report, RiskConfig())
    top = top_n_by_score(scored, n=2)
    assert len(top) == 2
    assert list(top["invoice_id"]) == [300, 100]  # score 100, then 65


def test_weight_for_returns_configured_value() -> None:
    """_weight_for looks up the correct weight attribute on the config."""
    config = RiskConfig(duplicate_weight=42.0)
    assert _weight_for("Duplicate", config) == 42.0
    assert _weight_for("Unknown", config) == 0.0


def test_format_reasons_joins_with_semicolons() -> None:
    """format_reasons produces a CSV-safe display string."""
    assert format_reasons(["Duplicate", "Anomaly"]) == "Duplicate; Anomaly"
    assert format_reasons([]) == ""
