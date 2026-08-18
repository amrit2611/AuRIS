"""Tests for the Groq-powered AI summary layer.

All tests use a mocked Groq client; no real API calls are made,
so CI does not require GROQ_API_KEY.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from auris.config import RiskConfig
from auris.summarize import _EMPTY_REPORT_MESSAGE, summarize_risks


def _fake_groq_response(text: str) -> SimpleNamespace:
    """Mimic the shape of a Groq chat completion: response.choices[0].message.content."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _mock_client(reply_text: str = "# AuRIS Risk Summary\n\nSummary body.") -> MagicMock:
    """Build a MagicMock Groq client whose chat.completions.create returns reply_text."""
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_groq_response(reply_text)
    return client


@pytest.fixture
def small_report() -> pd.DataFrame:
    """A 6-row report where vendor A appears in 2 risk types (overlap fixture)."""
    return pd.DataFrame([
        {"invoice_id": 1, "vendor": "A", "amount": 100.0, "date": "2025-01-01", "risk_type": "Duplicate"},
        {"invoice_id": 2, "vendor": "A", "amount": 100.0, "date": "2025-01-01", "risk_type": "Duplicate"},
        {"invoice_id": 3, "vendor": "A", "amount": 7500.0, "date": "2025-01-05", "risk_type": "Anomaly"},
        {"invoice_id": 4, "vendor": "D", "amount": 9999.0, "date": "2025-01-11", "risk_type": "Anomaly"},
        {"invoice_id": 5, "vendor": "C", "amount": float("nan"), "date": "2025-01-10", "risk_type": "Missing Data"},
        {"invoice_id": 6, "vendor": "B", "amount": 250.0, "date": "2025-01-07", "risk_type": "Duplicate"},
    ])


def test_summarize_risks_happy_path_calls_groq_with_expected_args(
    monkeypatch: pytest.MonkeyPatch, small_report: pd.DataFrame
) -> None:
    """Mock the Groq client and verify model, max_tokens, system, and prompt structure."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client("# AuRIS Risk Summary\n\n- Found duplicates and one anomaly.")

    result = summarize_risks(small_report, RiskConfig(), client=client)

    assert client.chat.completions.create.call_count == 1
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["max_tokens"] == 1024
    messages = kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    system_prompt = messages[0]["content"]
    assert system_prompt.startswith("You are a senior audit analyst")
    assert "FORBIDDEN PHRASES" in system_prompt
    assert "warrants review" in system_prompt
    assert "Priority Actions" in system_prompt
    assert messages[1]["role"] == "user"
    user_prompt = messages[1]["content"]
    assert "# Aggregates" in user_prompt
    assert "Counts and totals per risk_type" in user_prompt
    assert "Vendors flagged by multiple risk types" in user_prompt
    assert "Top transactions per risk_type" in user_prompt
    assert "Duplicate" in user_prompt
    assert "Anomaly" in user_prompt
    assert "Missing Data" in user_prompt
    assert "9999" in user_prompt
    assert result.startswith("# AuRIS Risk Summary")


def test_summarize_risks_input_prompt_includes_cross_check_overlap(
    monkeypatch: pytest.MonkeyPatch, small_report: pd.DataFrame
) -> None:
    """The overlap section names vendors that appear in 2+ risk types."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client()

    summarize_risks(small_report, RiskConfig(), client=client)

    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    overlap_section = user_prompt.split("# Vendors flagged by multiple risk types")[1].split("# Top transactions")[0]
    # Vendor A is in both Duplicate and Anomaly; it must appear in the overlap section.
    assert "A" in overlap_section
    assert "2 risk types" in overlap_section
    # Vendors B, C, D each appear in only one risk type; they must NOT be in this section.
    assert "B:" not in overlap_section
    assert "D:" not in overlap_section


def test_summarize_risks_empty_report_returns_canned_message_without_api_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty report short-circuits: returns the canned message, never hits the API."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client()

    result = summarize_risks(pd.DataFrame(), RiskConfig(), client=client)

    assert result == _EMPTY_REPORT_MESSAGE
    assert client.chat.completions.create.call_count == 0


def test_summarize_risks_missing_api_key_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, small_report: pd.DataFrame
) -> None:
    """When GROQ_API_KEY is unset, raise RuntimeError with a clear message."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarize_risks(small_report, RiskConfig())


def test_summarize_risks_respects_custom_model_and_max_tokens(
    monkeypatch: pytest.MonkeyPatch, small_report: pd.DataFrame
) -> None:
    """RiskConfig overrides for summary_model and summary_max_tokens are honoured."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client()
    config = RiskConfig(summary_model="llama-3.1-8b-instant", summary_max_tokens=2048)

    summarize_risks(small_report, config, client=client)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "llama-3.1-8b-instant"
    assert kwargs["max_tokens"] == 2048


def test_summarize_risks_returns_non_empty_markdown_string(
    monkeypatch: pytest.MonkeyPatch, small_report: pd.DataFrame
) -> None:
    """The function returns a non-empty string that looks like Markdown."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client("# Heading\n\n- bullet 1\n- bullet 2\n")

    result = summarize_risks(small_report, RiskConfig(), client=client)

    assert isinstance(result, str)
    assert len(result) > 0
    assert result.startswith("#")
