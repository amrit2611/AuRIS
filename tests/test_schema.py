"""Tests for LLM-driven column detection and the mapping helpers.

All tests use a mocked Groq client; no real API calls are made,
so CI does not require GROQ_API_KEY.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from auris.config import RiskConfig
from auris.schema import (
    REQUIRED_FIELDS,
    apply_mapping,
    detect_columns,
    parse_column_map_flag,
)


def _fake_groq_response(text: str) -> SimpleNamespace:
    """Mimic the shape of a Groq chat completion: response.choices[0].message.content."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _mock_client(reply_text: str) -> MagicMock:
    """Build a MagicMock Groq client whose chat.completions.create returns reply_text."""
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_groq_response(reply_text)
    return client


@pytest.fixture
def usaspending_like_df() -> pd.DataFrame:
    """A tiny DataFrame with USASpending-like column names (not AuRIS's schema)."""
    return pd.DataFrame([
        {"award_id_piid": "80NSSC24FA361", "recipient_name": "NEW TECH SOLUTIONS, INC.",
         "total_obligated_amount": 24225.00, "award_base_action_date": "2024-03-11"},
        {"award_id_piid": "80NSSC24FA362", "recipient_name": "FOUR LLC",
         "total_obligated_amount": 114935.53, "award_base_action_date": "2024-03-08"},
    ])


# ------------------------------------------------------------
# detect_columns()
# ------------------------------------------------------------

def test_detect_columns_happy_path_calls_groq_with_expected_args(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """Verify model, response_format, prompt structure, and returned mapping."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client(
        '{"vendor": "recipient_name", "amount": "total_obligated_amount", '
        '"date": "award_base_action_date", "invoice_id": "award_id_piid"}'
    )

    mapping = detect_columns(usaspending_like_df, RiskConfig(), client=client)

    assert client.chat.completions.create.call_count == 1
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "llama-3.3-70b-versatile"
    assert kwargs["response_format"] == {"type": "json_object"}
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "data schema mapper" in messages[0]["content"]
    user_prompt = messages[1]["content"]
    for header in usaspending_like_df.columns:
        assert header in user_prompt

    assert mapping == {
        "vendor": "recipient_name",
        "amount": "total_obligated_amount",
        "date": "award_base_action_date",
        "invoice_id": "award_id_piid",
    }


def test_detect_columns_handles_null_field_from_llm(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """When the LLM returns null for a field, the mapping preserves the null."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client(
        '{"vendor": "recipient_name", "amount": "total_obligated_amount", '
        '"date": "award_base_action_date", "invoice_id": null}'
    )

    mapping = detect_columns(usaspending_like_df, RiskConfig(), client=client)
    assert mapping["invoice_id"] is None
    assert mapping["vendor"] == "recipient_name"


def test_detect_columns_drops_hallucinated_column_names(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """When the LLM hallucinates a column name not in the CSV, the field becomes None."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client(
        '{"vendor": "recipient_name", "amount": "total_obligated_amount", '
        '"date": "made_up_date_column", "invoice_id": "award_id_piid"}'
    )

    mapping = detect_columns(usaspending_like_df, RiskConfig(), client=client)
    assert mapping["date"] is None
    assert mapping["vendor"] == "recipient_name"


def test_detect_columns_missing_api_key_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """When GROQ_API_KEY is unset, raise RuntimeError with a clear message."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        detect_columns(usaspending_like_df, RiskConfig())


def test_detect_columns_empty_dataframe_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detection on an empty DataFrame is a caller bug; raise ValueError."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with pytest.raises(ValueError, match="empty"):
        detect_columns(pd.DataFrame(), RiskConfig())


def test_detect_columns_malformed_json_raises(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """When the LLM returns non-JSON garbage, raise ValueError."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client("this is not JSON at all")
    with pytest.raises(ValueError, match="invalid JSON"):
        detect_columns(usaspending_like_df, RiskConfig(), client=client)


def test_detect_columns_missing_required_key_raises(
    monkeypatch: pytest.MonkeyPatch, usaspending_like_df: pd.DataFrame
) -> None:
    """When the LLM omits a required key, raise ValueError."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    client = _mock_client(
        '{"vendor": "recipient_name", "amount": "total_obligated_amount"}'
    )
    with pytest.raises(ValueError, match="missing required keys"):
        detect_columns(usaspending_like_df, RiskConfig(), client=client)


# ------------------------------------------------------------
# parse_column_map_flag()
# ------------------------------------------------------------

def test_parse_column_map_flag_parses_valid_comma_separated_pairs() -> None:
    """The CLI flag format 'k=v,k=v' round-trips into a dict."""
    result = parse_column_map_flag(
        "vendor=recipient_name,amount=total_usd,date=action_date,invoice_id=award_id"
    )
    assert result == {
        "vendor": "recipient_name",
        "amount": "total_usd",
        "date": "action_date",
        "invoice_id": "award_id",
    }


def test_parse_column_map_flag_rejects_unknown_field_names() -> None:
    """Only the four REQUIRED_FIELDS are accepted; anything else is a ValueError."""
    with pytest.raises(ValueError, match="unknown --column-map field"):
        parse_column_map_flag("vendor=foo,bogus=bar")


def test_parse_column_map_flag_rejects_missing_equals() -> None:
    """Entries without '=' are rejected."""
    with pytest.raises(ValueError, match="expected 'field=column' pairs"):
        parse_column_map_flag("vendor recipient_name")


# ------------------------------------------------------------
# apply_mapping()
# ------------------------------------------------------------

def test_apply_mapping_renames_columns_to_auris_schema(
    usaspending_like_df: pd.DataFrame,
) -> None:
    """A complete mapping renames all four columns; original df is unchanged."""
    mapping = {
        "vendor": "recipient_name",
        "amount": "total_obligated_amount",
        "date": "award_base_action_date",
        "invoice_id": "award_id_piid",
    }
    renamed = apply_mapping(usaspending_like_df, mapping)
    for field in REQUIRED_FIELDS:
        assert field in renamed.columns
    # Original DataFrame is untouched.
    assert "recipient_name" in usaspending_like_df.columns


def test_apply_mapping_skips_none_and_absent_columns(
    usaspending_like_df: pd.DataFrame,
) -> None:
    """None values and columns absent from the DataFrame are silently skipped."""
    mapping = {
        "vendor": "recipient_name",
        "amount": None,
        "date": "not_a_real_column",
        "invoice_id": "award_id_piid",
    }
    renamed = apply_mapping(usaspending_like_df, mapping)
    assert "vendor" in renamed.columns
    assert "invoice_id" in renamed.columns
    # amount and date should NOT be created.
    assert "amount" not in renamed.columns
    assert "date" not in renamed.columns
