"""LLM-driven column detection: map arbitrary CSV headers to AuRIS's schema.

AuRIS's pipeline expects four columns: `vendor`, `amount`, `date`,
`invoice_id`. Real-world CSVs never come with those exact names.
Rather than shipping a per-source adapter script for every possible
data source, this module asks the same Groq / Llama layer that
writes the executive summary to also read the CSV headers plus a
few sample rows and return the mapping.

Usage:
    from auris.schema import detect_columns
    mapping = detect_columns(df, config)
    # mapping = {"vendor": "recipient_name", "amount": "total_usd", ...}
    df = df.rename(columns={v: k for k, v in mapping.items() if v})

The detected mapping is a *suggestion*. Callers are expected to show
it to the user and let them override each field via a dropdown or
CLI flag before the pipeline runs.

Security note: this function sends CSV headers and up to 3 sample
rows to the Groq API. Do not pass CSVs that contain secrets or
credentials to `detect_columns`. Column *values* used as sample rows
are visible to the model.
"""
import json
import logging
import os
from typing import Optional

import pandas as pd

from auris.config import DEFAULT_CONFIG, RiskConfig

logger = logging.getLogger("auris")

REQUIRED_FIELDS = ("vendor", "amount", "date", "invoice_id")

_SAMPLE_ROWS = 3
# Above this column count, we skip sample rows in the prompt to stay under
# Groq's free-tier per-request token limit. Column names alone still give
# the LLM enough signal for the common cases.
_WIDE_CSV_THRESHOLD = 40
# Cap on any individual cell value length in the sample rows, to keep long
# text fields (descriptions, addresses) from blowing up the prompt.
_MAX_CELL_CHARS = 120

_SYSTEM_PROMPT = (
    "You are a data schema mapper. You will be given the headers and a few "
    "sample rows of a CSV file. Your job is to identify which columns map to "
    "the four required fields of an audit-risk pipeline. Return only valid "
    "JSON matching the exact schema requested. Do not add prose or "
    "explanation outside the JSON object."
)


def _truncate_cell(value: object) -> object:
    """Cap string cells at _MAX_CELL_CHARS; leave non-strings alone."""
    if isinstance(value, str) and len(value) > _MAX_CELL_CHARS:
        return value[:_MAX_CELL_CHARS] + "..."
    return value


def _build_prompt(headers: list[str], sample_rows: list[dict] | None) -> str:
    """Build the user-message body from the header list and (optional) sample rows.

    For CSVs with many columns, `sample_rows` is passed as None to keep the
    prompt under Groq's free-tier per-request token limit; the LLM has to
    infer the mapping from column names alone.
    """
    body = (
        "Map the following CSV to an audit-risk schema with exactly these "
        "four required fields:\n"
        "- vendor: name of the party being paid or receiving the transaction "
        "(company or individual)\n"
        "- amount: numeric monetary value of the transaction\n"
        "- date: transaction date, in any parseable format\n"
        "- invoice_id: unique identifier for the transaction, invoice, or "
        "award\n\n"
        f"CSV headers: {headers}\n\n"
    )
    if sample_rows:
        body += (
            f"Sample rows (up to {_SAMPLE_ROWS}):\n"
            f"{json.dumps(sample_rows, default=str, indent=2)}\n\n"
        )
    else:
        body += (
            "(The CSV has too many columns to include sample rows. "
            "Infer the mapping from column names alone.)\n\n"
        )
    body += (
        "Return ONLY a JSON object with exactly these four keys: vendor, "
        "amount, date, invoice_id. Each value must be either the exact name "
        "of a column from the CSV headers list, or null if no column maps to "
        "that field.\n\n"
        'Example: {"vendor": "recipient_name", "amount": "total_usd", '
        '"date": "action_date", "invoice_id": "award_id"}'
    )
    return body


def detect_columns(
    df: pd.DataFrame,
    config: RiskConfig = DEFAULT_CONFIG,
    client: Optional[object] = None,
) -> dict[str, Optional[str]]:
    """Ask the LLM to map CSV headers to AuRIS's four required fields.

    Returns a dict with keys `vendor`, `amount`, `date`, `invoice_id`.
    Each value is either the name of a column in `df`, or `None` if the
    LLM could not find a match. Raises RuntimeError if `GROQ_API_KEY`
    is unset. Raises ValueError if the LLM returns a malformed response.
    `client` is an optional pre-built Groq client, useful for tests.
    """
    if df is None or df.empty:
        raise ValueError("cannot detect columns on an empty DataFrame.")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is required for LLM column "
            "detection. Get a free key from https://console.groq.com and "
            "set it in your environment (e.g. via a .env file). Alternatively, "
            "pass --column-map on the CLI to specify the mapping manually."
        )

    if client is None:
        from groq import Groq
        client = Groq()

    headers = list(df.columns)
    include_samples = len(headers) <= _WIDE_CSV_THRESHOLD
    if include_samples:
        raw_samples = df.head(_SAMPLE_ROWS).to_dict(orient="records")
        sample_rows = [
            {k: _truncate_cell(v) for k, v in row.items()} for row in raw_samples
        ]
    else:
        sample_rows = None
    user_prompt = _build_prompt(headers, sample_rows)

    logger.info(
        "requesting column mapping: model=%s, headers=%d, samples=%s",
        config.summary_model, len(headers),
        "included" if include_samples else "omitted (wide CSV)",
    )

    response = client.chat.completions.create(
        model=config.summary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=256,
        response_format={"type": "json_object"},
    )

    if not response.choices:
        raise ValueError("LLM returned no choices in the response.")
    text = response.choices[0].message.content or ""
    text = text.strip()
    if not text:
        raise ValueError("LLM returned an empty response.")

    try:
        mapping = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(mapping, dict):
        raise ValueError(f"LLM returned {type(mapping).__name__}, not a JSON object.")

    missing_keys = [k for k in REQUIRED_FIELDS if k not in mapping]
    if missing_keys:
        raise ValueError(
            f"LLM response missing required keys: {missing_keys}. Got: {list(mapping.keys())}"
        )

    result: dict[str, Optional[str]] = {}
    for key in REQUIRED_FIELDS:
        value = mapping[key]
        if value is None or value == "":
            result[key] = None
            continue
        if not isinstance(value, str):
            raise ValueError(
                f"LLM mapped '{key}' to a {type(value).__name__}, expected string or null."
            )
        if value not in headers:
            logger.warning(
                "LLM mapped '%s' to column '%s' which is not in CSV headers; dropping.",
                key, value,
            )
            result[key] = None
            continue
        result[key] = value

    logger.info("column mapping detected: %s", result)
    return result


def parse_column_map_flag(flag_value: str) -> dict[str, str]:
    """Parse the CLI --column-map value into a mapping dict.

    Format: comma-separated pairs of `auris_field=source_column`. Example:
        vendor=recipient_name,amount=total_usd,date=action_date,invoice_id=award_id
    Whitespace around keys and values is stripped. Raises ValueError on
    malformed input or unknown auris_field keys.
    """
    mapping: dict[str, str] = {}
    for raw_pair in flag_value.split(","):
        pair = raw_pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(
                f"invalid --column-map entry '{pair}': expected 'field=column' pairs "
                "separated by commas."
            )
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in REQUIRED_FIELDS:
            raise ValueError(
                f"unknown --column-map field '{key}': expected one of {REQUIRED_FIELDS}."
            )
        if not value:
            raise ValueError(f"--column-map entry '{pair}' has an empty value.")
        mapping[key] = value
    return mapping


def apply_mapping(df: pd.DataFrame, mapping: dict[str, Optional[str]]) -> pd.DataFrame:
    """Rename columns in df according to the mapping.

    Values that are None are ignored (the auris field is left unmapped).
    Values pointing at columns that don't exist in df are also ignored.
    Returns a new DataFrame with renamed columns; does not mutate the input.
    """
    rename: dict[str, str] = {}
    for auris_field, source_col in mapping.items():
        if source_col is None:
            continue
        if source_col not in df.columns:
            logger.warning(
                "mapping references column '%s' not in DataFrame; skipping.",
                source_col,
            )
            continue
        rename[source_col] = auris_field
    return df.rename(columns=rename)
