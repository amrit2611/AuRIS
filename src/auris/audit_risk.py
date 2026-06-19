"""AuRIS audit pipeline.

Loads a transactions CSV, runs five statistical risk checks (duplicates,
high-value anomalies, missing data, vendor frequency outliers, per-vendor
amount deviations) and writes a consolidated CSV report plus five PNG
visualizations to the output directory.
"""
import argparse
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from auris.config import DEFAULT_CONFIG, RiskConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA = PROJECT_ROOT / "data" / "transactions.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "output"

logger = logging.getLogger("auris")


def configure_logging(verbosity: int) -> None:
    """Configure the root auris logger from a -v/-q derived verbosity count."""
    level = logging.INFO
    if verbosity >= 1:
        level = logging.DEBUG
    elif verbosity <= -1:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_data(file_path: Path) -> Optional[pd.DataFrame]:
    """Read a transactions CSV from disk; returns None on failure."""
    try:
        data = pd.read_csv(file_path)
        logger.info("data loaded successfully: %d rows", len(data))
        logger.debug("head:\n%s", data.head())
        return data
    except FileNotFoundError:
        logger.error("%s not found.", file_path)
        return None
    except Exception as e:
        logger.error("error loading data: %s", e)
        return None


def check_duplicates(data: pd.DataFrame) -> pd.DataFrame:
    """Flag rows that repeat the same (vendor, amount, date) triple."""
    duplicates = data[data.duplicated(subset = ['vendor', 'amount', 'date'], keep=False)].copy()
    if not duplicates.empty:
        duplicates['risk_type'] = 'Duplicate'
        logger.info("duplicate transactions found: %d", len(duplicates))
        logger.debug("duplicates:\n%s", duplicates)
    else:
        logger.info("no duplicates found.")
    return duplicates


def check_anomalies(data: pd.DataFrame, config: RiskConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Flag transactions whose amount exceeds the configured quantile threshold."""
    if 'amount' not in data.columns:
        logger.error("'amount' column missing.")
        return pd.DataFrame()
    threshold = data['amount'].quantile(config.anomaly_quantile)
    anomalies = data[data['amount'] > threshold].copy()
    if not anomalies.empty:
        anomalies['risk_type'] = 'Anomaly'
        logger.info("high valued anomalies found: %d (threshold=%.2f)", len(anomalies), threshold)
        logger.debug("anomalies:\n%s", anomalies)
    else:
        logger.info("no anomalies found.")
    return anomalies


def check_missing(data: pd.DataFrame) -> pd.DataFrame:
    """Flag rows with at least one missing value across any column."""
    missing = data[data.isna().any(axis=1)].copy()
    if not missing.empty:
        missing['risk_type'] = 'Missing Data'
        logger.info("missing data rows found: %d", len(missing))
        logger.debug("missing:\n%s", missing)
    else:
        logger.info("no missing data found.")
    return missing


def check_vendor_frequency(data: pd.DataFrame, config: RiskConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Flag transactions for vendors above the configured frequency quantile."""
    vendor_counts = data['vendor'].value_counts()
    threshold = vendor_counts.quantile(config.vendor_frequency_quantile)
    frequent_vendors = vendor_counts[vendor_counts > threshold].index
    if len(frequent_vendors) > 0:
        frequent_data = data[data['vendor'].isin(frequent_vendors)].copy()
        frequent_data['risk_type'] = 'High Frequency'
        logger.info(
            "vendors with high transaction frequency found: %d vendors, %d rows (threshold=%.0f)",
            len(frequent_vendors), len(frequent_data), threshold,
        )
        logger.debug("frequent vendor rows:\n%s", frequent_data)
        return frequent_data
    logger.info("no vendors with high frequency found.")
    return pd.DataFrame()


def check_ml_anomalies(data: pd.DataFrame, config: RiskConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Flag multivariate anomalies via Isolation Forest over (amount, vendor, date).

    Imports scikit-learn lazily so the base pipeline keeps working when
    sklearn isn't installed. Returns an empty DataFrame when the model
    can't run (missing columns, too few rows, or sklearn unavailable).
    """
    required = ['amount', 'vendor', 'date']
    if not all(col in data.columns for col in required):
        logger.error("required columns missing for ML anomaly detection.")
        return pd.DataFrame()

    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import LabelEncoder
    except ImportError:
        logger.warning("scikit-learn not installed; skipping ML anomaly check.")
        return pd.DataFrame()

    ml_data = data.dropna(subset=['amount']).copy()
    if len(ml_data) < 20:
        logger.info("not enough rows (%d) for ML anomaly detection; skipping.", len(ml_data))
        return pd.DataFrame()

    encoder = LabelEncoder()
    ml_data['vendor_encoded'] = encoder.fit_transform(ml_data['vendor'])
    ml_data['date_ordinal'] = pd.to_datetime(ml_data['date']).map(lambda d: d.toordinal())

    features = ml_data[['amount', 'vendor_encoded', 'date_ordinal']]
    model = IsolationForest(
        contamination=config.ml_contamination,
        random_state=config.ml_random_state,
        n_estimators=config.ml_n_estimators,
    )
    ml_data['ml_score'] = model.fit_predict(features)

    ml_anomalies = ml_data[ml_data['ml_score'] == -1].copy()
    ml_anomalies = ml_anomalies.drop(columns=['vendor_encoded', 'date_ordinal', 'ml_score'])

    if not ml_anomalies.empty:
        ml_anomalies['risk_type'] = 'ML Anomaly'
        logger.info(
            "ML-detected anomalies (Isolation Forest): %d (contamination=%.2f)",
            len(ml_anomalies), config.ml_contamination,
        )
        logger.debug("ml anomalies:\n%s", ml_anomalies.head(10))
    else:
        logger.info("no ML anomalies detected.")
    return ml_anomalies


def check_amount_deviation(data: pd.DataFrame, config: RiskConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Flag transactions whose amount falls outside the configured per-vendor band."""
    if 'amount' not in data.columns:
        logger.error("'amount' column missing.")
        return pd.DataFrame()
    vendor_avg = data.groupby('vendor')['amount'].mean()
    low = config.deviation_low_multiplier
    high = config.deviation_high_multiplier
    deviations = pd.DataFrame()
    for vendor in data['vendor'].unique():
        vendor_data = data[data['vendor'] == vendor]
        avg = vendor_avg[vendor]
        vendor_deviations = vendor_data[(vendor_data['amount'] < low * avg) | (vendor_data['amount'] > high * avg)].copy()
        if not vendor_deviations.empty:
            vendor_deviations['risk_type'] = 'Amount Deviation'
            deviations = pd.concat([deviations, vendor_deviations])
    if not deviations.empty:
        logger.info("amount deviations found: %d", len(deviations))
        logger.debug("deviations:\n%s", deviations)
    else:
        logger.info("no amount deviations found.")
    return deviations


def plot_histogram(data: pd.DataFrame, output_dir: Path) -> None:
    """Save a histogram of transaction amounts to amount_distribution.png."""
    if 'amount' not in data.columns:
        logger.error("cannot plot histogram without 'amount' column.")
        return
    plt.figure(figsize=(8, 6))
    data['amount'].hist(bins=20)
    plt.title('Transaction Amount Distribution')
    plt.xlabel('Amount')
    plt.ylabel('Frequency')
    plt.savefig(output_dir / 'amount_distribution.png')
    plt.close()
    logger.info("histogram saved as amount_distribution.png")


def plot_vendor_frequency(data: pd.DataFrame, output_dir: Path) -> None:
    """Save a bar chart of transaction counts per vendor to vendor_frequency.png."""
    vendor_counts = data['vendor'].value_counts()
    plt.figure(figsize=(10, 6))
    vendor_counts.plot(kind='bar')
    plt.title('Transaction count by Vendor')
    plt.xlabel('Vendor')
    plt.ylabel('Number of Transactions')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_dir / 'vendor_frequency.png')
    plt.close()
    logger.info("vendor frequency chart saved as vendor_frequency.png")


def plot_time_series(data: pd.DataFrame, output_dir: Path) -> None:
    """Save a scatter plot of amounts over time with a rolling-mean trend line."""
    if 'amount' not in data.columns or 'date' not in data.columns:
        logger.error("'amount' or 'date' column missing for time series plot.")
        return
    data['date'] = pd.to_datetime(data['date'])
    plt.figure(figsize=(10, 6))
    plt.scatter(data['date'], data['amount'], color='blue', alpha=0.5)
    data = data.sort_values('date')
    rolling_mean = data['amount'].rolling(window=5, min_periods=1).mean()
    plt.plot(data['date'], rolling_mean, color='red', linewidth=2, label='Trend')
    plt.title('Transaction Amounts Over Time')
    plt.xlabel('Date')
    plt.ylabel('Amount')
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / 'time_series.png')
    plt.close()
    logger.info("time series chart saved as time_series.png")


def plot_risk_distribution(report: pd.DataFrame, output_dir: Path) -> None:
    """Save a pie chart of risk-type proportions to risk_distribution.png."""
    if report.empty or 'risk_type' not in report.columns:
        logger.error("no report data or 'risk_type' is missing.")
        return
    risk_counts = report['risk_type'].value_counts()
    plt.figure(figsize=(8,6))
    plt.pie(risk_counts, labels=risk_counts.index, autopct='%1.1f%%', startangle=90)
    plt.title('Distribution of Risk Types')
    plt.axis('equal')
    plt.savefig(output_dir / 'risk_distribution.png')
    plt.close()
    logger.info("risk distribution pie chart saved as risk_distribution.png")


def plot_vendor_date_heatmap(data: pd.DataFrame, output_dir: Path) -> None:
    """Save a vendor-by-date transaction-count heatmap to vendor_date_heatmap.png."""
    if 'vendor' not in data.columns or 'date' not in data.columns:
        logger.error("'vendor' or 'date' column missing for heatmap.")
        return
    data['date'] = pd.to_datetime(data['date']).dt.strftime('%Y-%m-%d')
    pivot_table = data.pivot_table(values='amount', index='date', columns='vendor', aggfunc='count', fill_value=0)
    plt.figure(figsize=(12, 8))
    sns.heatmap(pivot_table, cmap='YlOrRd')
    plt.title('Transaction Density by Vendor and Date')
    plt.xlabel('Vendor')
    plt.ylabel('Date')
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(output_dir / 'vendor_date_heatmap.png')
    plt.close()
    logger.info("vendor-date heatmap saved as vendor_date_heatmap.png")


def generate_report(
    duplicates: pd.DataFrame,
    anomalies: pd.DataFrame,
    missing: pd.DataFrame,
    frequent_vendors: pd.DataFrame,
    amount_deviations: pd.DataFrame,
    output_dir: Path,
    ml_anomalies: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Concatenate every per-check DataFrame and write the consolidated risks_report.csv.

    ml_anomalies is an optional sixth frame (from check_ml_anomalies). When
    omitted, the report shape stays identical to the original five-check
    pipeline so existing call sites and tests continue to work.
    """
    if ml_anomalies is None:
        ml_anomalies = pd.DataFrame()
    report = pd.concat(
        [duplicates, anomalies, missing, frequent_vendors, amount_deviations, ml_anomalies],
        ignore_index=True,
    )
    if not report.empty:
        report = report.sort_values(['risk_type', 'vendor', 'amount', 'date'])
        report.to_csv(output_dir / 'risks_report.csv', index=False)
        logger.info("risk report saved as risks_report.csv (%d total rows)", len(report))
    else:
        logger.info("no risks found. no report generated.")
    return report


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for input CSV, output directory, thresholds and verbosity."""
    parser = argparse.ArgumentParser(description="AuRIS: Audit Risk Identification System")
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_DATA,
                        help="Path to transactions CSV file")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Directory for output reports and charts")
    parser.add_argument("--anomaly-quantile", type=float, default=DEFAULT_CONFIG.anomaly_quantile,
                        help="Quantile threshold for high-value anomaly detection (default 0.9)")
    parser.add_argument("--vendor-frequency-quantile", type=float,
                        default=DEFAULT_CONFIG.vendor_frequency_quantile,
                        help="Quantile threshold for vendor frequency outliers (default 0.9)")
    parser.add_argument("--deviation-low", type=float, default=DEFAULT_CONFIG.deviation_low_multiplier,
                        help="Per-vendor low-end multiplier for amount deviation (default 0.2)")
    parser.add_argument("--deviation-high", type=float, default=DEFAULT_CONFIG.deviation_high_multiplier,
                        help="Per-vendor high-end multiplier for amount deviation (default 2.0)")
    parser.add_argument("--enable-ml", action="store_true",
                        help="Also run Isolation Forest multivariate anomaly detection")
    parser.add_argument("--ml-contamination", type=float, default=DEFAULT_CONFIG.ml_contamination,
                        help="Expected fraction of outliers for Isolation Forest (default 0.05)")
    parser.add_argument("--ml-n-estimators", type=int, default=DEFAULT_CONFIG.ml_n_estimators,
                        help="Number of trees in the Isolation Forest (default 200)")
    parser.add_argument("--ml-random-state", type=int, default=DEFAULT_CONFIG.ml_random_state,
                        help="Random seed for deterministic ML runs (default 42)")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity (-v for DEBUG)")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                        help="Decrease verbosity (-q for WARNING only)")
    return parser.parse_args()


def main() -> None:
    """CLI entry point: load data, run all checks, write the report, render plots."""
    args = parse_args()
    configure_logging(args.verbose - args.quiet)
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    config = RiskConfig(
        anomaly_quantile=args.anomaly_quantile,
        vendor_frequency_quantile=args.vendor_frequency_quantile,
        deviation_low_multiplier=args.deviation_low,
        deviation_high_multiplier=args.deviation_high,
        ml_contamination=args.ml_contamination,
        ml_n_estimators=args.ml_n_estimators,
        ml_random_state=args.ml_random_state,
    )

    logger.info("starting AuRIS: Audit Risk Identification System")
    data = load_data(args.input)
    if data is None:
        return
    duplicates = check_duplicates(data)
    anomalies = check_anomalies(data, config)
    missing = check_missing(data)
    frequent_vendors = check_vendor_frequency(data, config)
    amount_deviations = check_amount_deviation(data, config)
    ml_anomalies = check_ml_anomalies(data, config) if args.enable_ml else None
    report = generate_report(
        duplicates, anomalies, missing, frequent_vendors, amount_deviations, output_dir,
        ml_anomalies=ml_anomalies,
    )
    plot_histogram(data, output_dir)
    plot_vendor_frequency(data, output_dir)
    plot_time_series(data, output_dir)
    plot_risk_distribution(report, output_dir)
    plot_vendor_date_heatmap(data, output_dir)
    logger.info("AuRIS analysis complete!")


if __name__ == "__main__":
    main()
