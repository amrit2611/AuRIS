"""Tunable thresholds for the AuRIS risk checks.

Default values are chosen to produce an actionable review pool rather
than a firehose. Industry practice (ISA 320 materiality, PCAOB
risk-based sampling, Big-4 audit tools like ACL / IDEA) typically
surfaces 1 to 5 percent of transactions for manual review. Anything
above 10 percent starts to signal that the thresholds are too loose
to be useful.

AuRIS's defaults aim for the 5 percent zone on typical CSVs. Users
who want a wider net (early-stage screening) can loosen the sliders
in the sidebar; users who want a tighter net (senior auditor's
follow-up pool) can tighten them.

Level 2 (risk scoring): each of the six risk checks has a weight
that contributes to a per-row score (0 to 100). Defaults are
calibrated so a row flagged by every check maxes the scale, and so
the "loud" checks (Duplicate, Anomaly, ML) contribute more than the
"noisy" checks (High Frequency, Missing Data) that fire on wide
real-world CSVs.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Thresholds and scoring weights for the AuRIS risk checks.

    Attributes:
        anomaly_quantile: Quantile of `amount` above which a row is flagged
            as a high-value anomaly. Default 0.99 (top 1%, aligns with the
            "unusual amount" review pool audit teams typically inspect).
        vendor_frequency_quantile: Quantile of per-vendor transaction counts
            above which a vendor is flagged. Default 0.99 (top 1%). On wide
            skewed real-world data (e.g. federal contracting where a few
            primes hold thousands of contracts) 0.95 flags too many
            transactions to be actionable; 0.99 keeps the review pool tight.
        deviation_low_multiplier: Per-vendor multiplier; rows whose amount
            is below `mean * this` are flagged. Default 0.1 (below 10% of
            the vendor's mean, wide enough to catch data-entry errors).
        deviation_high_multiplier: Per-vendor multiplier; rows whose amount
            is above `mean * this` are flagged. Default 3.0 (above 300% of
            vendor's mean, aligns with 3-sigma outlier convention).
        ml_contamination: Expected fraction of outliers for Isolation Forest.
            Default 0.02 (2%, matches typical fraud-prevalence assumptions in
            financial-transaction ML literature).
        ml_n_estimators: Number of trees in the Isolation Forest ensemble.
            Default 200.
        ml_random_state: Random seed for deterministic ML runs. Default 42.
        summary_model: Groq model id used by the AI summary layer.
            Default "llama-3.3-70b-versatile" (free tier).
        summary_max_tokens: Hard cap on summary output length in tokens.
            Default 1024.
        duplicate_weight: Points contributed to the risk score when a row
            is flagged by the Duplicate check. Default 25. Duplicates are
            the highest-signal audit finding (real double-payments).
        anomaly_weight: Points for the high-value Anomaly check. Default 20.
        deviation_weight: Points for the per-vendor Amount Deviation check.
            Default 15.
        missing_weight: Points for the Missing Data check. Default 10
            (data-hygiene signal, not fraud).
        frequency_weight: Points for the High Frequency (top vendor) check.
            Default 10 (noisy on skewed real data; kept low intentionally).
        ml_weight: Points for the Isolation Forest ML Anomaly check.
            Default 20 (catches multivariate patterns the statistical
            checks miss).

    Weights sum to 100 by default, so a row flagged by every check
    scores 100. Users can override any weight via the RiskConfig
    constructor; scoring caps the per-row total at 100.
    """

    anomaly_quantile: float = 0.99
    vendor_frequency_quantile: float = 0.99
    deviation_low_multiplier: float = 0.1
    deviation_high_multiplier: float = 3.0
    ml_contamination: float = 0.02
    ml_n_estimators: int = 200
    ml_random_state: int = 42
    summary_model: str = "llama-3.3-70b-versatile"
    summary_max_tokens: int = 1024

    # Level 2 scoring weights (0-100 per row, sum of contributing checks).
    duplicate_weight: float = 25.0
    anomaly_weight: float = 20.0
    deviation_weight: float = 15.0
    missing_weight: float = 10.0
    frequency_weight: float = 10.0
    ml_weight: float = 20.0


DEFAULT_CONFIG = RiskConfig()
