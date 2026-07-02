"""Shared pytest fixtures for the AuRIS test suite."""
import logging

import pandas as pd
import pytest

# `auris` is installed via `pip install -e .` (see pyproject.toml); no
# sys.path manipulation needed.

# Quiet the auris logger during tests.
logging.getLogger("auris").addHandler(logging.NullHandler())
logging.getLogger("auris").propagate = False


@pytest.fixture
def sample_transactions() -> pd.DataFrame:
    """A 12-row in-memory transactions DataFrame with known risk patterns.

    Expected flags under DEFAULT_CONFIG:
      - 2 duplicates (rows 1, 2: same vendor/amount/date)
      - 1 anomaly (row 12: 9999, well above the 90th percentile)
      - 1 missing-data row (row 11: NaN amount)
      - High-frequency vendor: A (8 transactions vs <=2 for others)
      - 2 amount-deviation rows for vendor A (row 7 amount=5, row 8 amount=500)
    """
    return pd.DataFrame([
        {"invoice_id": 1,  "vendor": "A", "amount": 100.0,  "date": "2025-01-01"},
        {"invoice_id": 2,  "vendor": "A", "amount": 100.0,  "date": "2025-01-01"},
        {"invoice_id": 3,  "vendor": "A", "amount": 110.0,  "date": "2025-01-02"},
        {"invoice_id": 4,  "vendor": "A", "amount": 90.0,   "date": "2025-01-03"},
        {"invoice_id": 5,  "vendor": "A", "amount": 105.0,  "date": "2025-01-04"},
        {"invoice_id": 6,  "vendor": "A", "amount": 95.0,   "date": "2025-01-05"},
        {"invoice_id": 7,  "vendor": "A", "amount": 5.0,    "date": "2025-01-06"},
        {"invoice_id": 8,  "vendor": "A", "amount": 500.0,  "date": "2025-01-07"},
        {"invoice_id": 9,  "vendor": "B", "amount": 200.0,  "date": "2025-01-08"},
        {"invoice_id": 10, "vendor": "B", "amount": 220.0,  "date": "2025-01-09"},
        {"invoice_id": 11, "vendor": "C", "amount": float("nan"), "date": "2025-01-10"},
        {"invoice_id": 12, "vendor": "D", "amount": 9999.0, "date": "2025-01-11"},
    ])
