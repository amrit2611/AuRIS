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
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Thresholds for the statistical, ML, and AI-summary risk checks.

    Attributes:
        anomaly_quantile: Quantile of `amount` above which a row is flagged
            as a high-value anomaly. Default 0.99 (top 1%, aligns with the
            "unusual amount" review pool audit teams typically inspect).
        vendor_frequency_quantile: Quantile of per-vendor transaction counts
            above which a vendor is flagged. Default 0.95 (top 5%, matches
            "high-activity vendor" heuristic used in kickback screens).
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
    """

    anomaly_quantile: float = 0.99
    vendor_frequency_quantile: float = 0.95
    deviation_low_multiplier: float = 0.1
    deviation_high_multiplier: float = 3.0
    ml_contamination: float = 0.02
    ml_n_estimators: int = 200
    ml_random_state: int = 42
    summary_model: str = "llama-3.3-70b-versatile"
    summary_max_tokens: int = 1024


DEFAULT_CONFIG = RiskConfig()
