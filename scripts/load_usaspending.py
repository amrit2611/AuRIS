"""Adapter: convert a USASpending.gov Prime Award Contracts CSV to AuRIS's schema.

USASpending's Contracts CSV has ~286 columns per row. This script keeps
only the five AuRIS cares about, renames them, and writes a slim CSV
ready to feed into `python -m auris`.

Usage:
    python3 scripts/load_usaspending.py \\
        -i data/usaspending_raw.csv \\
        -o data/usaspending_sample.csv \\
        --fiscal-year 2024 -v
"""
import argparse
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("auris.load_usaspending")

_COLUMN_MAP = {
    "award_id_piid": "invoice_id",
    "recipient_name": "vendor",
    "total_obligated_amount": "amount",
    "award_base_action_date": "date",
    "prime_award_base_transaction_description": "description",
}


def load_usaspending(
    input_path: Path,
    output_path: Path,
    fiscal_year: int | None = None,
) -> pd.DataFrame:
    """Read a USASpending Contracts CSV, project to AuRIS schema, write to output_path.

    When `fiscal_year` is given, keep only rows whose award_base_action_date
    falls inside the US federal fiscal year (Oct 1 of prior year through
    Sep 30 of that year). Useful for narrowing to a specific reporting period.
    """
    logger.info("reading %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    logger.info("read %d rows, %d columns", len(df), df.shape[1])

    missing = [c for c in _COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(
            f"expected columns not found in input: {missing}. "
            "Is this a USASpending Contracts_PrimeAwardSummaries CSV?"
        )

    df = df[list(_COLUMN_MAP.keys())].rename(columns=_COLUMN_MAP)

    # Parse dates; drop rows whose date is unparseable.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["date"])
    if before != len(df):
        logger.info("dropped %d rows with unparseable dates", before - len(df))

    if fiscal_year is not None:
        start = pd.Timestamp(f"{fiscal_year - 1}-10-01")
        end = pd.Timestamp(f"{fiscal_year}-09-30")
        before = len(df)
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        logger.info(
            "filtered to FY%d (%s to %s): kept %d of %d rows",
            fiscal_year, start.date(), end.date(), len(df), before,
        )

    # Serialise date back to string; audit_risk.py parses on read.
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df = df[["invoice_id", "vendor", "amount", "date", "description"]]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("writing %d rows to %s", len(df), output_path)
    df.to_csv(output_path, index=False)
    return df


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Convert a USASpending Contracts CSV to AuRIS's schema."
    )
    parser.add_argument("-i", "--input", type=Path, required=True,
                        help="Path to the raw USASpending Contracts CSV")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Path to write the AuRIS-schema CSV")
    parser.add_argument("--fiscal-year", type=int, default=None,
                        help="Optional: filter to a specific US federal fiscal year "
                             "(e.g. 2024 keeps Oct 1 2023 through Sep 30 2024).")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable INFO-level logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    load_usaspending(args.input, args.output, fiscal_year=args.fiscal_year)


if __name__ == "__main__":
    main()
