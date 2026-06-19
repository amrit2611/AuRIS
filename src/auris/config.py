"""Tunable thresholds for the AuRIS risk checks.

All knobs the auditor might want to dial without editing pipeline code
live here. The defaults match the original hardcoded values so existing
runs produce identical output.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Thresholds for the five statistical risk checks.

    Attributes:
        anomaly_quantile: Quantile of `amount` above which a row is flagged
            as a high-value anomaly. Default 0.9 (top 10%).
        vendor_frequency_quantile: Quantile of per-vendor transaction counts
            above which a vendor is flagged. Default 0.9 (top 10%).
        deviation_low_multiplier: Per-vendor multiplier; rows whose amount
            is below `mean * this` are flagged. Default 0.2 (<20% of mean).
        deviation_high_multiplier: Per-vendor multiplier; rows whose amount
            is above `mean * this` are flagged. Default 2.0 (>200% of mean).
    """

    anomaly_quantile: float = 0.9
    vendor_frequency_quantile: float = 0.9
    deviation_low_multiplier: float = 0.2
    deviation_high_multiplier: float = 2.0


DEFAULT_CONFIG = RiskConfig()
