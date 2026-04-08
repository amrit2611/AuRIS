import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder

def load_data(file_path):
    try:
        data = pd.read_csv(file_path)
        print("data loaded successfully:")
        print(data.head())
        return data
    except FileNotFoundError:
        print("error: transactions.csv not found.")
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


def check_ml_anomalies(data):
    """Use Isolation Forest to detect multivariate anomalies across amount, vendor, and date patterns."""
    required = ['amount', 'vendor', 'date']
    if not all(col in data.columns for col in required):
        print("\nError: required columns missing for ML anomaly detection.")
        return pd.DataFrame()

    ml_data = data.dropna(subset=['amount']).copy()
    if len(ml_data) < 20:
        print("\nNot enough data for ML anomaly detection.")
        return pd.DataFrame()

    le = LabelEncoder()
    ml_data['vendor_encoded'] = le.fit_transform(ml_data['vendor'])
    ml_data['date_ordinal'] = pd.to_datetime(ml_data['date']).map(lambda d: d.toordinal())

    features = ml_data[['amount', 'vendor_encoded', 'date_ordinal']]

    model = IsolationForest(contamination=0.05, random_state=42, n_estimators=200)
    ml_data['ml_score'] = model.fit_predict(features)

    ml_anomalies = ml_data[ml_data['ml_score'] == -1].copy()
    ml_anomalies['risk_type'] = 'ML Anomaly'
    ml_anomalies = ml_anomalies.drop(columns=['vendor_encoded', 'date_ordinal', 'ml_score'])

    if not ml_anomalies.empty:
        print(f"\nML-detected anomalies (Isolation Forest): {len(ml_anomalies)} found")
        print(ml_anomalies.head(10))
    else:
        print("\nNo ML anomalies detected.")
    return ml_anomalies


def plot_histogram(data):
    if 'amount' not in data.columns:
        print("\nError: cannot plot without 'amount column.")
        return
    plt.figure(figsize=(8, 6))
    data['amount'].hist(bins=20)
    plt.title('Transaction Amount Distribution')
    plt.xlabel('Amount')
    plt.ylabel('Frequency')
    plt.savefig('amount_distribution.png')
    plt.close()
    print("\nHistogram saved as amount_distribution.png")
    
    
def plot_vendor_frequency(data):
    vendor_counts = data['vendor'].value_counts()
    plt.figure(figsize=(10, 6))
    vendor_counts.plot(kind='bar')
    plt.title('Transaction count by Vendor')
    plt.xlabel('Vendor')
    plt.ylabel('Number of Transactions')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('vendor_frequency.png')
    plt.close()
    print("\nVendor frequency chart saved as vendor_frequency.png")
    
    
def plot_time_series(data):
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
    plt.savefig('time_series.png')
    plt.close()
    print("\nTime series chart saved as time_series.png")
    
    
def plot_risk_distribution(report):
    if report.empty or 'risk_type' not in report.columns:
        print("\nError: no report data or 'risk_type' is missing.")
        return
    risk_counts = report['risk_type'].value_counts()
    plt.figure(figsize=(8,6))
    plt.pie(risk_counts, labels=risk_counts.index, autopct='%1.1f%%', startangle=90)
    plt.title('Distribution of Risk Types')
    plt.axis('equal')
    plt.savefig('risk_distribution.png')
    plt.close()
    print("\nRisk distribution pie chart saved as risk_distribution.png")
    
    
def plot_vendor_date_heatmap(data):
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
    plt.savefig('vendor_date_heatmap.png')
    plt.close()
    print("\nVendor-Date heatmap saved as vendor_date_heatmap.png")
    
    
def generate_report(duplicates, anomalies, missing, frequent_vendors, amount_deviations, ml_anomalies):
    report = pd.concat([duplicates, anomalies, missing, frequent_vendors, amount_deviations, ml_anomalies], ignore_index=True)
    if not report.empty:
        report = report.sort_values(['risk_type', 'vendor', 'amount', 'date'])
        report.to_csv('risks_report.csv', mode='a', index=False)
        print("\nRisk report saved as risks_report.csv")
    else:
        print("\nNo risks found. No report generated.")
    return report


def main():
    print("Starting AuRIS: Audit Risk Identification System")
    data = load_data('transactions.csv')
    if data is None:
        return
    duplicates = check_duplicates(data)
    anomalies = check_anomalies(data)
    missing = check_missing(data)
    frequent_vendors = check_vendor_frequency(data)
    amount_deviations = check_amount_deviation(data)
    ml_anomalies = check_ml_anomalies(data)
    report = generate_report(duplicates, anomalies, missing, frequent_vendors, amount_deviations, ml_anomalies)
    plot_histogram(data)
    plot_vendor_frequency(data)
    plot_time_series(data)
    plot_risk_distribution(report)
    plot_vendor_date_heatmap(data)
    print("\nAuRIS analysis complete!")
    
    
if __name__ == "__main__":
    main()