"""Tunable thresholds for the AuRIS risk checks.

All knobs the auditor might want to dial without editing pipeline code
live here. The defaults match the original hardcoded values so existing
runs produce identical output.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Thresholds for the statistical, ML, and AI-summary risk checks.

    Attributes:
        anomaly_quantile: Quantile of `amount` above which a row is flagged
            as a high-value anomaly. Default 0.9 (top 10%).
        vendor_frequency_quantile: Quantile of per-vendor transaction counts
            above which a vendor is flagged. Default 0.9 (top 10%).
        deviation_low_multiplier: Per-vendor multiplier; rows whose amount
            is below `mean * this` are flagged. Default 0.2 (<20% of mean).
        deviation_high_multiplier: Per-vendor multiplier; rows whose amount
            is above `mean * this` are flagged. Default 2.0 (>200% of mean).
        ml_contamination: Expected fraction of outliers for Isolation Forest.
            Default 0.05 (about 5% of rows flagged).
        ml_n_estimators: Number of trees in the Isolation Forest ensemble.
            Default 200.
        ml_random_state: Random seed for deterministic ML runs. Default 42.
        summary_model: Claude model id used by the AI summary layer.
            Default "claude-haiku-4-5" (cheapest tier, sufficient for short
            executive summaries).
        summary_max_tokens: Hard cap on summary output length in tokens.
            Default 1024 (keeps cost predictable; one CFO-readable summary).
    """

    anomaly_quantile: float = 0.9
    vendor_frequency_quantile: float = 0.9
    deviation_low_multiplier: float = 0.2
    deviation_high_multiplier: float = 2.0
    ml_contamination: float = 0.05
    ml_n_estimators: int = 200
    ml_random_state: int = 42
    summary_model: str = "claude-haiku-4-5"
    summary_max_tokens: int = 1024


DEFAULT_CONFIG = RiskConfig()
