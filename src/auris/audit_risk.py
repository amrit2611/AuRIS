import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA = PROJECT_ROOT / "data" / "transactions.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "output"


def load_data(file_path):
    try:
        data = pd.read_csv(file_path)
        print("data loaded successfully:")
        print(data.head())
        return data
    except FileNotFoundError:
        print(f"error: {file_path} not found.")
        return None
    except Exception as e:
        print(f"error loading data: {e}")
        return None
    

def check_duplicates(data):
    duplicates = data[data.duplicated(subset = ['vendor', 'amount', 'date'], keep=False)].copy()
    if not duplicates.empty:
        duplicates['risk_type'] = 'Duplicate'
        print("\nDuplicate transactions found:")
        print(duplicates)
    else:
        print("\nNo duplicates found.")
    return duplicates


def check_anomalies(data):
    if 'amount' not in data.columns:
        print("\nerror: 'amount' column missing.")
        return pd.DataFrame()
    threshold = data['amount'].quantile(0.9)
    anomalies = data[data['amount'] > threshold].copy()
    if not anomalies.empty:
        anomalies['risk_type'] = 'Anomaly'
        print("\nHigh valued anomalies found:")
        print(anomalies)
    else:
        print("\nNo anomalies found.")
    return anomalies


def check_missing(data):
    missing = data[data.isna().any(axis=1)].copy()
    if not missing.empty:
        missing['risk_type'] = 'Missing Data'
        print("\nMissing data found:")
        print(missing)
    else:
        print("\nNo missing data found.")
    return missing




def check_vendor_frequency(data):
    vendor_counts = data['vendor'].value_counts()
    threshold = vendor_counts.quantile(0.9)
    frequent_vendors = vendor_counts[vendor_counts > threshold].index
    if len(frequent_vendors) > 0:
        frequent_data = data[data['vendor'].isin(frequent_vendors)].copy()
        frequent_data['risk_type'] = 'High Frequency'
        print("\nVendors with High Transaction Frequency found:")
        print(frequent_data)
        return frequent_data
    else: 
        print("\nNo vendors with high frequency found.")
        return pd.DataFrame()
    

def check_amount_deviation(data):
    if 'amount' not in data.columns:
        print("\nError: 'amount' column missing.")
        return pd.DataFrame()
    vendor_avg = data.groupby('vendor')['amount'].mean()
    deviations = pd.DataFrame()
    for vendor in data['vendor'].unique():
        vendor_data = data[data['vendor'] == vendor]
        avg = vendor_avg[vendor]
        vendor_deviations = vendor_data[(vendor_data['amount'] < 0.2 * avg) | (vendor_data['amount'] > 2 * avg)].copy()
        if not vendor_deviations.empty:
            vendor_deviations['risk_type'] = 'Amount Deviation'
            deviations = pd.concat([deviations, vendor_deviations])
    if not deviations.empty:
        print("\nAmount Deviations found:")
        print(deviations)
    else:
        print("\nNo amount deviations found.")
    return deviations


def plot_histogram(data, output_dir):
    if 'amount' not in data.columns:
        print("\nError: cannot plot without 'amount column.")
        return
    plt.figure(figsize=(8, 6))
    data['amount'].hist(bins=20)
    plt.title('Transaction Amount Distribution')
    plt.xlabel('Amount')
    plt.ylabel('Frequency')
    plt.savefig(output_dir / 'amount_distribution.png')
    plt.close()
    print("\nHistogram saved as amount_distribution.png")
    
    
def plot_vendor_frequency(data, output_dir):
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
    print("\nVendor frequency chart saved as vendor_frequency.png")
    
    
def plot_time_series(data, output_dir):
    if 'amount' not in data.columns or 'date' not in data.columns:
        print("\nError: 'amount' or 'date' column missing.")
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
    print("\nTime series chart saved as time_series.png")
    
    
def plot_risk_distribution(report, output_dir):
    if report.empty or 'risk_type' not in report.columns:
        print("\nError: no report data or 'risk_type' is missing.")
        return
    risk_counts = report['risk_type'].value_counts()
    plt.figure(figsize=(8,6))
    plt.pie(risk_counts, labels=risk_counts.index, autopct='%1.1f%%', startangle=90)
    plt.title('Distribution of Risk Types')
    plt.axis('equal')
    plt.savefig(output_dir / 'risk_distribution.png')
    plt.close()
    print("\nRisk distribution pie chart saved as risk_distribution.png")
    
    
def plot_vendor_date_heatmap(data, output_dir):
    if 'vendor' not in data.columns or 'date' not in data.columns:
        print("\nError: 'vendor' or 'date' column missing.")
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
    print("\nVendor-Date heatmap saved as vendor_date_heatmap.png")
    
    
def generate_report(duplicates, anomalies, missing, frequent_vendors, amount_deviations, output_dir):
    report = pd.concat([duplicates, anomalies, missing, frequent_vendors, amount_deviations], ignore_index=True)
    if not report.empty:
        report = report.sort_values(['risk_type', 'vendor', 'amount', 'date'])
        report.to_csv(output_dir / 'risks_report.csv', index=False)
        print("\nRisk report saved as risks_report.csv")
    else:
        print("\nNo risks found. No report generated.")
    return report


def parse_args():
    parser = argparse.ArgumentParser(description="AuRIS: Audit Risk Identification System")
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_DATA,
                        help="Path to transactions CSV file")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Directory for output reports and charts")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Starting AuRIS: Audit Risk Identification System")
    data = load_data(args.input)
    if data is None:
        return
    duplicates = check_duplicates(data)
    anomalies = check_anomalies(data)
    missing = check_missing(data)
    frequent_vendors = check_vendor_frequency(data)
    amount_deviations = check_amount_deviation(data)
    report = generate_report(duplicates, anomalies, missing, frequent_vendors, amount_deviations, output_dir)
    plot_histogram(data, output_dir)
    plot_vendor_frequency(data, output_dir)
    plot_time_series(data, output_dir)
    plot_risk_distribution(report, output_dir)
    plot_vendor_date_heatmap(data, output_dir)
    print("\nAuRIS analysis complete!")


if __name__ == "__main__":
    main()