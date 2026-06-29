"""Groq-powered natural-language summaries of an AuRIS risk report.

Reads `GROQ_API_KEY` from the environment, sends a compact projection
of the risk report (top-N highest-amount rows per `risk_type`) to the
Groq API (Llama 3.3 70B by default), and returns a CFO-readable
Markdown summary.

Designed for cost: the prompt is bounded by `_TOP_N_PER_TYPE * num_risk_types`
rows regardless of input size, and the output is capped via
`RiskConfig.summary_max_tokens`. Empty reports short-circuit without
calling the API at all. Groq's free tier (no credit card required)
runs Llama 3.3 70B with 14,400 requests/day, so typical development
and demo usage costs nothing.
"""
import logging
import os
from typing import Optional

import pandas as pd

from auris.config import DEFAULT_CONFIG, RiskConfig

logger = logging.getLogger("auris")

_TOP_N_PER_TYPE = 5
_EMPTY_REPORT_MESSAGE = (
    "# AuRIS Risk Summary\n\n"
    "No risks were detected in the analysed transactions. "
    "All checks passed under the current thresholds.\n"
)
_SYSTEM_PROMPT = (
    "You are a senior audit analyst writing executive summaries for a CFO. "
    "You will receive a risk report grouped by risk_type. Each group shows the "
    "highest-amount transactions flagged by that check.\n\n"
    "Produce a Markdown document with this exact structure:\n"
    "1. A top-level heading: `# AuRIS Risk Summary`\n"
    "2. A 3 to 5 bullet executive summary under `## Executive Summary`\n"
    "3. One short paragraph per risk_type under `## Findings by Risk Type`, "
    "each prefixed with a `### <risk_type>` subheading, explaining what was "
    "flagged and why it warrants review.\n\n"
    "Be concise, factual, and CFO-readable. Do not invent transactions; only "
    "describe what is in the report. Do not include preamble or closing notes."
)


def _build_prompt(report: pd.DataFrame) -> str:
    """Build the user-message body from the top-N rows per risk_type."""
    sections: list[str] = []
    for risk_type, group in report.groupby("risk_type"):
        top_rows = group.nlargest(_TOP_N_PER_TYPE, "amount", keep="first")
        sections.append(f"## {risk_type} ({len(group)} total rows flagged)")
        sections.append(
            "Top {n} by amount:".format(n=min(_TOP_N_PER_TYPE, len(group)))
        )
        for _, row in top_rows.iterrows():
            vendor = row.get("vendor", "unknown")
            amount = row.get("amount", "n/a")
            date = row.get("date", "n/a")
            sections.append(f"- vendor={vendor}, amount={amount}, date={date}")
        sections.append("")
    return "\n".join(sections).strip()


def summarize_risks(
    report: pd.DataFrame,
    config: RiskConfig = DEFAULT_CONFIG,
    client: Optional[object] = None,
) -> str:
    """Generate a Markdown executive summary of the risk report via Groq.

    Returns a canned no-risk message and does not hit the API when the
    report is empty. Raises RuntimeError if `GROQ_API_KEY` is unset.
    `client` is an optional pre-built Groq client, useful for tests.
    """
    if report is None or report.empty:
        logger.info("risk report is empty; skipping API call.")
        return _EMPTY_REPORT_MESSAGE

    if "risk_type" not in report.columns:
        raise ValueError("report must include a 'risk_type' column.")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is required for the summary "
            "feature. Get a free key from https://console.groq.com and set "
            "it in your environment (e.g. via a .env file)."
        )

    if client is None:
        from groq import Groq
        client = Groq()

    user_prompt = _build_prompt(report)
    logger.info(
        "requesting AI summary: model=%s, max_tokens=%d, prompt_chars=%d",
        config.summary_model, config.summary_max_tokens, len(user_prompt),
    )

    response = client.chat.completions.create(
        model=config.summary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=config.summary_max_tokens,
    )

    if not response.choices:
        logger.warning("AI summary response had no choices; returning canned message.")
        return _EMPTY_REPORT_MESSAGE
    text = response.choices[0].message.content or ""
    text = text.strip()
    if not text:
        logger.warning("AI summary response was empty; returning canned message.")
        return _EMPTY_REPORT_MESSAGE
    return text
