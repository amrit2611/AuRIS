"""Groq-powered natural-language summaries of an AuRIS risk report.

Reads `GROQ_API_KEY` from the environment, sends a structured projection
of the risk report (aggregates, cross-check overlaps, top-N rows per
risk_type) to the Groq API (Llama 3.3 70B by default), and returns a
CFO-readable Markdown summary.

Designed for both cost and quality:

- The prompt is bounded: aggregates plus a fixed top-N rows per risk
  type, regardless of input size, so the input token cost is flat.
- The system prompt forbids generic filler phrases and demands
  specific vendor names, dollar amounts, and prioritised actions.
- Empty reports short-circuit without calling the API at all.

Groq's free tier (no credit card required) runs Llama 3.3 70B at
14,400 requests/day, so typical development and demo usage costs
nothing.
"""
import logging
import os
from typing import Optional

import pandas as pd

from auris.config import DEFAULT_CONFIG, RiskConfig

logger = logging.getLogger("auris")

_TOP_N_PER_TYPE = 5
_TOP_N_OVERLAP_VENDORS = 10
_TOP_N_BY_SCORE = 15
_EMPTY_REPORT_MESSAGE = (
    "# AuRIS Risk Summary\n\n"
    "No risks were detected in the analysed transactions. "
    "All checks passed under the current thresholds.\n"
)
_SYSTEM_PROMPT = """You are a senior audit analyst writing an executive summary for a CFO who has not seen the underlying data. The CFO will read this in 60 seconds and decide what to investigate first.

You will receive a structured risk report with aggregates, cross-check overlap data, and top transactions per risk type. Use only what is in the input. Do not invent vendors, amounts, dates, or risk types. Every claim must reference a specific number, vendor name, or risk type from the input.

Produce a Markdown document with exactly this structure and these three sections, in this order:

# AuRIS Risk Summary

## Executive Summary
3 to 5 bullets. Each bullet must state a SPECIFIC finding tied to a number or vendor from the input.
- WRONG: "There are potential issues that warrant review."
- WRONG: "Several transactions may indicate anomalies."
- RIGHT: "JKL Pvt is flagged by 3 of the 5 checks, accounting for $2.4M of total flagged exposure."
- RIGHT: "Amount Deviation flagged 394 rows totalling $58M, the largest category by dollar value."

## Findings by Risk Type
One short paragraph per risk_type, prefixed with a `### <risk_type>` subheading. Each paragraph must include the count of flagged rows for that type, the total dollar amount for that type, and at least one specific vendor or transaction example with its amount. Describe what makes this category interesting in this specific report. Do not pad with generic phrases.

## Priority Actions
2 or 3 numbered actions, ordered by importance. Each action must name a SPECIFIC vendor, risk type, or threshold.
- WRONG: "Review flagged transactions."
- WRONG: "Implement stricter controls."
- RIGHT: "Investigate Atlas Materials first: it appears in 4 risk types and totals $1.9M of flagged exposure."
- RIGHT: "Tighten the Anomaly quantile above 0.9. 999 flagged rows is too many to triage manually."

FORBIDDEN PHRASES. Do not use these anywhere in the output, with or without minor rewording:
- "warrants review"
- "requires investigation"
- "may indicate"
- "potential issues"
- "needs to be reviewed"
- "should be examined"
- "further analysis is needed"
- "ensure accuracy and legitimacy"
- "warrant further review"

FORMATTING RULES. Follow these strictly:
- Do NOT wrap numbers, dollar amounts, dates, or vendor names in backticks or code fences. Write them as plain text so they render inline with the sentence, not as monospace code blocks.
- Format dollar amounts with a leading dollar sign and comma thousands separators, e.g. $2,483,900.14 (never `2483900.14` or `$2483900`).
- Format dates in a natural style, e.g. "on 2024-07-01" or "in July 2024", not as code.
- Use bold sparingly, only to emphasise the most important vendor or dollar figure in each section.

Do not include preamble, closing notes, or meta commentary about the report itself."""


def _build_scored_section(scored: pd.DataFrame) -> list[str]:
    """Build the "top N by risk score" section from a scored DataFrame.

    Included in the prompt only when the caller passes a scored report.
    Gives the model a ranked triage queue to prioritise its priority
    actions instead of guessing from top-by-amount rows.
    """
    if scored is None or scored.empty or "risk_score" not in scored.columns:
        return []
    sections = ["# Top rows by risk score (triage queue, highest first)"]
    top = scored.head(_TOP_N_BY_SCORE)
    for _, row in top.iterrows():
        vendor = row.get("vendor", "unknown")
        amount = row.get("amount", "n/a")
        date = row.get("date", "n/a")
        score = float(row.get("risk_score", 0.0))
        reasons = row.get("reasons", [])
        if isinstance(reasons, (list, tuple, set)):
            reasons_str = ", ".join(reasons)
        else:
            reasons_str = str(reasons)
        sections.append(
            f"- score={score:.0f}/100, vendor={vendor}, amount={amount}, "
            f"date={date}, checks_fired=[{reasons_str}]"
        )
    sections.append("")
    return sections


def _build_prompt(report: pd.DataFrame, scored: pd.DataFrame | None = None) -> str:
    """Build a structured user-message body: aggregates, overlaps, then top rows per type."""
    sections: list[str] = []

    total_rows = len(report)
    has_amount = "amount" in report.columns
    amount_series = report["amount"].dropna() if has_amount else pd.Series(dtype=float)
    total_amount = float(amount_series.sum()) if not amount_series.empty else 0.0

    sections.append("# Aggregates")
    sections.append(f"- Total flagged rows across all checks: {total_rows}")
    if total_amount > 0:
        sections.append(f"- Total flagged amount (sum of non-null amounts): ${total_amount:,.2f}")
    if "date" in report.columns:
        dates = pd.to_datetime(report["date"], errors="coerce").dropna()
        if not dates.empty:
            sections.append(f"- Date range of flagged rows: {dates.min().date()} to {dates.max().date()}")
    sections.append("")

    sections.append("# Counts and totals per risk_type")
    type_groups = report.groupby("risk_type")
    type_summary = type_groups.agg(
        count=("risk_type", "size"),
        total_amount=("amount", "sum") if has_amount else ("risk_type", "size"),
    )
    type_summary = type_summary.sort_values("total_amount", ascending=False)
    for risk_type, row in type_summary.iterrows():
        if has_amount:
            sections.append(
                f"- {risk_type}: {int(row['count'])} rows, total ${float(row['total_amount']):,.2f}"
            )
        else:
            sections.append(f"- {risk_type}: {int(row['count'])} rows")
    sections.append("")

    sections.append("# Vendors flagged by multiple risk types (cross-check overlap)")
    if "vendor" in report.columns:
        vendor_types = (
            report.groupby("vendor")["risk_type"].nunique().sort_values(ascending=False)
        )
        repeat_vendors = vendor_types[vendor_types >= 2].head(_TOP_N_OVERLAP_VENDORS)
        if not repeat_vendors.empty:
            vendor_totals = (
                report.groupby("vendor")["amount"].sum() if has_amount else None
            )
            for vendor, n_types in repeat_vendors.items():
                types_for_vendor = sorted(report.loc[report["vendor"] == vendor, "risk_type"].unique())
                line = f"- {vendor}: flagged by {int(n_types)} risk types ({', '.join(types_for_vendor)})"
                if vendor_totals is not None:
                    amount = float(vendor_totals.get(vendor, 0.0))
                    line += f", total amount ${amount:,.2f}"
                sections.append(line)
        else:
            sections.append("- (none, no vendor appears in more than one risk type)")
    else:
        sections.append("- (vendor column missing from report)")
    sections.append("")

    sections.append("# Top transactions per risk_type (highest amount first)")
    for risk_type, group in type_groups:
        sections.append(f"## {risk_type}")
        if has_amount:
            top_rows = group.nlargest(_TOP_N_PER_TYPE, "amount", keep="first")
        else:
            top_rows = group.head(_TOP_N_PER_TYPE)
        for _, row in top_rows.iterrows():
            vendor = row.get("vendor", "unknown")
            amount = row.get("amount", "n/a")
            date = row.get("date", "n/a")
            sections.append(f"- vendor={vendor}, amount={amount}, date={date}")
        sections.append("")

    # Optional Level 2 scoring section: adds the ranked triage queue so the
    # model's Priority Actions can name specific high-scoring rows directly.
    sections.extend(_build_scored_section(scored))

    return "\n".join(sections).strip()


def summarize_risks(
    report: pd.DataFrame,
    config: RiskConfig = DEFAULT_CONFIG,
    client: Optional[object] = None,
    scored: Optional[pd.DataFrame] = None,
) -> str:
    """Generate a Markdown executive summary of the risk report via Groq.

    Returns a canned no-risk message and does not hit the API when the
    report is empty. Raises RuntimeError if `GROQ_API_KEY` is unset.
    `client` is an optional pre-built Groq client, useful for tests.

    If `scored` is passed (a DataFrame produced by
    `auris.scoring.score_report`), an extra "Top rows by risk score"
    section is added to the prompt so the model's Priority Actions can
    directly reference the ranked triage queue.
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

    user_prompt = _build_prompt(report, scored=scored)
    logger.info(
        "requesting AI summary: model=%s, max_tokens=%d, prompt_chars=%d, scored=%s",
        config.summary_model, config.summary_max_tokens, len(user_prompt),
        "yes" if scored is not None and not scored.empty else "no",
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
