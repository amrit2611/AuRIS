"""Weighted risk scoring on top of the six risk checks.

The five statistical checks plus the Isolation Forest ML check each
produce a flat list of flagged rows tagged with a `risk_type`. On
real-world data those lists overlap heavily: a Fortune 500 defense
contractor gets flagged by High Frequency, its largest contracts
also fire the Anomaly check, and both fire again in the ML pass.
The result is a report where the same source row appears multiple
times, and where "top by amount" is a bad triage signal (a $22B
Boeing contract shows up first even if a $500 duplicate payment is
a stronger fraud indicator).

`score_report` collapses those overlapping check-hits into one row
per source transaction and assigns each a 0-100 risk score by
summing the weights of the checks that fired. The result is a
proper triage queue: sort by score descending, look at the top N,
send the rest to bulk review. This is the model real audit tools
(ACL, IDEA, Wolters Kluwer) use, and it's the fix for the "6,222
rows flagged - which ones do I look at?" problem the raw report
has on wide real-world CSVs.

Reason codes: every scored row carries a `reasons` field listing
the check names that fired. Downstream (AI summary, dashboard
Findings tab) uses those to explain the score.
"""
import logging
from typing import Iterable

import pandas as pd

from auris.config import DEFAULT_CONFIG, RiskConfig

logger = logging.getLogger("auris")

# Maps the risk_type string produced by each check function to the
# corresponding weight attribute on RiskConfig. Keeps the check
# functions themselves unaware of scoring.
_RISK_TYPE_TO_WEIGHT_FIELD: dict[str, str] = {
    "Duplicate": "duplicate_weight",
    "Anomaly": "anomaly_weight",
    "Amount Deviation": "deviation_weight",
    "Missing Data": "missing_weight",
    "High Frequency": "frequency_weight",
    "ML Anomaly": "ml_weight",
}

_MAX_SCORE = 100.0


def _weight_for(risk_type: str, config: RiskConfig) -> float:
    """Look up the configured weight for a given risk_type string."""
    field = _RISK_TYPE_TO_WEIGHT_FIELD.get(risk_type)
    if field is None:
        logger.warning("unknown risk_type '%s'; treating as zero-weight.", risk_type)
        return 0.0
    return float(getattr(config, field, 0.0))


def score_report(
    report: pd.DataFrame,
    config: RiskConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """Collapse overlapping check-hits into one scored row per source transaction.

    Given the concatenated report from all six risk checks, return a
    new DataFrame where:

    - Each source row (identified by `invoice_id`) appears exactly once.
    - `risk_score` (0 to 100) is the sum of the weights of the checks
      that fired on that row, capped at 100.
    - `reasons` is a sorted list of the risk_type names that fired.
    - Rows are sorted by `risk_score` descending, so the caller gets a
      ready-made triage queue.

    Rows without a usable `invoice_id` are kept unaggregated (each
    check-hit becomes its own scored row) so no data is silently
    lost, but they still get a `risk_score` and `reasons` field.

    Empty input returns an empty DataFrame with the new columns
    present so downstream code can rely on them existing.
    """
    if report is None or report.empty:
        return pd.DataFrame(columns=list(getattr(report, "columns", [])) + ["risk_score", "reasons"])

    if "risk_type" not in report.columns:
        raise ValueError("report must include a 'risk_type' column for scoring.")

    working = report.copy()
    working["_weight"] = working["risk_type"].map(
        lambda rt: _weight_for(rt, config)
    ).astype(float)

    # Rows without invoice_id are aggregated by their DataFrame index instead
    # (each row becomes its own group), so they still get a score.
    if "invoice_id" not in working.columns:
        logger.warning(
            "report has no 'invoice_id' column; scoring per row without dedup."
        )
        working["risk_score"] = working["_weight"].clip(upper=_MAX_SCORE)
        working["reasons"] = working["risk_type"].apply(lambda rt: [rt])
        result = working.drop(columns=["_weight"])
        return result.sort_values("risk_score", ascending=False).reset_index(drop=True)

    # Split rows with and without invoice_id.
    has_id = working["invoice_id"].notna()
    with_id = working.loc[has_id]
    without_id = working.loc[~has_id]

    scored_parts: list[pd.DataFrame] = []

    if not with_id.empty:
        grouped = with_id.groupby("invoice_id", sort=False, dropna=False)
        first_rows = grouped.first().drop(columns=["_weight"], errors="ignore")
        scores = grouped["_weight"].sum().clip(upper=_MAX_SCORE)
        reasons = grouped["risk_type"].agg(lambda types: sorted(set(types)))
        aggregated = first_rows.assign(
            risk_score=scores,
            reasons=reasons,
        ).reset_index()
        scored_parts.append(aggregated)

    if not without_id.empty:
        no_id = without_id.copy()
        no_id["risk_score"] = no_id["_weight"].clip(upper=_MAX_SCORE)
        no_id["reasons"] = no_id["risk_type"].apply(lambda rt: [rt])
        no_id = no_id.drop(columns=["_weight"])
        scored_parts.append(no_id)

    if not scored_parts:
        empty = working.drop(columns=["_weight", "risk_type"], errors="ignore").iloc[0:0].copy()
        empty["risk_score"] = pd.Series(dtype=float)
        empty["reasons"] = pd.Series(dtype=object)
        return empty

    result = pd.concat(scored_parts, ignore_index=True)

    # Drop the now-redundant risk_type column: identity is in `reasons`.
    if "risk_type" in result.columns:
        result = result.drop(columns=["risk_type"])

    logger.info(
        "scored %d unique rows (from %d check-hits); "
        "top score=%.1f, median=%.1f",
        len(result), len(report),
        float(result["risk_score"].max()) if not result.empty else 0.0,
        float(result["risk_score"].median()) if not result.empty else 0.0,
    )

    return result.sort_values("risk_score", ascending=False).reset_index(drop=True)


def top_n_by_score(scored: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Return the top N rows by risk_score. Assumes `scored` is already sorted."""
    if scored is None or scored.empty:
        return scored
    return scored.head(n)


def format_reasons(reasons: Iterable[str]) -> str:
    """Format a reasons list for display or CSV export."""
    return "; ".join(reasons) if reasons else ""
