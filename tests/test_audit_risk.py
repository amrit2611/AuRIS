"""Behavior tests for the five risk-check functions and the report aggregator."""
import pandas as pd

from auris.audit_risk import (
    check_amount_deviation,
    check_anomalies,
    check_duplicates,
    check_gstin_validity,
    check_missing,
    check_vendor_frequency,
    generate_report,
)
from auris.config import RiskConfig
from auris.gstin import compute_gstin_checksum


def test_check_duplicates_finds_matching_triples(sample_transactions):
    result = check_duplicates(sample_transactions)
    assert len(result) == 2
    assert set(result["invoice_id"]) == {1, 2}
    assert (result["risk_type"] == "Duplicate").all()


def test_check_duplicates_empty_when_none(sample_transactions):
    unique = sample_transactions.drop_duplicates(subset=["vendor", "amount", "date"])
    assert check_duplicates(unique).empty


def test_check_anomalies_flags_top_quantile(sample_transactions):
    result = check_anomalies(sample_transactions)
    assert 12 in result["invoice_id"].tolist()
    assert (result["risk_type"] == "Anomaly").all()


def test_check_anomalies_respects_config_override(sample_transactions):
    loose = check_anomalies(sample_transactions, RiskConfig(anomaly_quantile=0.99))
    tight = check_anomalies(sample_transactions, RiskConfig(anomaly_quantile=0.5))
    assert len(tight) >= len(loose)


def test_check_anomalies_missing_amount_column_returns_empty():
    df = pd.DataFrame([{"vendor": "A", "date": "2025-01-01"}])
    assert check_anomalies(df).empty


def test_check_missing_flags_nan_rows(sample_transactions):
    result = check_missing(sample_transactions)
    assert len(result) == 1
    assert result["invoice_id"].iloc[0] == 11
    assert (result["risk_type"] == "Missing Data").all()


def test_check_vendor_frequency_flags_busiest_vendor(sample_transactions):
    result = check_vendor_frequency(sample_transactions)
    assert not result.empty
    assert set(result["vendor"].unique()) == {"A"}
    assert (result["risk_type"] == "High Frequency").all()


def test_check_amount_deviation_flags_outliers(sample_transactions):
    result = check_amount_deviation(sample_transactions)
    invoice_ids = set(result["invoice_id"])
    assert {7, 8}.issubset(invoice_ids)
    assert (result["risk_type"] == "Amount Deviation").all()


def test_check_amount_deviation_widening_band_drops_flags(sample_transactions):
    narrow = check_amount_deviation(sample_transactions)
    wide = check_amount_deviation(
        sample_transactions,
        RiskConfig(deviation_low_multiplier=0.0, deviation_high_multiplier=1000.0),
    )
    assert len(wide) <= len(narrow)


def test_generate_report_concatenates_all_checks(tmp_path, sample_transactions):
    duplicates = check_duplicates(sample_transactions)
    anomalies = check_anomalies(sample_transactions)
    missing = check_missing(sample_transactions)
    frequent = check_vendor_frequency(sample_transactions)
    deviations = check_amount_deviation(sample_transactions)
    report = generate_report(duplicates, anomalies, missing, frequent, deviations, tmp_path)

    assert (tmp_path / "risks_report.csv").exists()
    assert not report.empty
    assert set(report["risk_type"].unique()).issubset(
        {"Duplicate", "Anomaly", "Missing Data", "High Frequency", "Amount Deviation"}
    )


def test_generate_report_empty_writes_no_file(tmp_path):
    empty = pd.DataFrame()
    report = generate_report(empty, empty, empty, empty, empty, tmp_path)
    assert report.empty
    assert not (tmp_path / "risks_report.csv").exists()


# ---------------------------------------------------------------------------
# check_gstin_validity
# ---------------------------------------------------------------------------

def _valid_gstin(base14: str) -> str:
    """Build a syntactically + checksum-valid GSTIN from a 14-char prefix."""
    return base14 + compute_gstin_checksum(base14)


def test_check_gstin_validity_returns_empty_when_column_absent(sample_transactions):
    """Legacy CSVs without a vendor_gstin column must not get flagged."""
    assert "vendor_gstin" not in sample_transactions.columns
    assert check_gstin_validity(sample_transactions).empty


def test_check_gstin_validity_flags_missing_malformed_and_bad_checksum():
    good = _valid_gstin("27AAPFU0939F1Z")
    bad_checksum = good[:-1] + ("A" if good[-1] != "A" else "B")
    df = pd.DataFrame([
        {"invoice_id": 1, "vendor": "A", "vendor_gstin": good},
        {"invoice_id": 2, "vendor": "B", "vendor_gstin": ""},           # missing
        {"invoice_id": 3, "vendor": "C", "vendor_gstin": "27ABC"},       # malformed length
        {"invoice_id": 4, "vendor": "D", "vendor_gstin": bad_checksum},  # bad check digit
        {"invoice_id": 5, "vendor": "E", "vendor_gstin": _valid_gstin("29ABCDE1234F1Z")},
    ])
    result = check_gstin_validity(df)
    assert set(result["invoice_id"]) == {2, 3, 4}
    assert (result["risk_type"] == "Invalid GSTIN").all()


def test_check_gstin_validity_handles_null_values():
    """NaN GSTIN values are treated as invalid (missing data)."""
    df = pd.DataFrame([
        {"invoice_id": 1, "vendor_gstin": _valid_gstin("27AAPFU0939F1Z")},
        {"invoice_id": 2, "vendor_gstin": None},
        {"invoice_id": 3, "vendor_gstin": float("nan")},
    ])
    result = check_gstin_validity(df)
    assert set(result["invoice_id"]) == {2, 3}


def test_generate_report_includes_gstin_invalid_when_passed(tmp_path, sample_transactions):
    """The optional gstin_invalid param flows into the concatenated report."""
    duplicates = check_duplicates(sample_transactions)
    gstin_bad = pd.DataFrame([
        {"invoice_id": 99, "vendor": "X", "vendor_gstin": "", "risk_type": "Invalid GSTIN"},
    ])
    empty = pd.DataFrame()
    report = generate_report(
        duplicates, empty, empty, empty, empty, tmp_path, gstin_invalid=gstin_bad,
    )
    assert "Invalid GSTIN" in set(report["risk_type"].unique())


def test_generate_report_omits_gstin_when_not_passed(tmp_path, sample_transactions):
    """When gstin_invalid is None, the report shape stays unchanged."""
    duplicates = check_duplicates(sample_transactions)
    empty = pd.DataFrame()
    report = generate_report(duplicates, empty, empty, empty, empty, tmp_path)
    assert "Invalid GSTIN" not in set(report["risk_type"].unique())
