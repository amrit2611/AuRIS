# AuRIS - Audit Risk Identification System

Welcome to **AuRIS** (Audit Risk Identification System), a Python-based tool designed to automate the identification of financial risks in transaction data. Inspired by the auditing needs of large corporations like ITC, AuRIS helps detect duplicates, anomalies, missing data, and unusual vendor patterns, providing actionable insights through detailed reports and visualizations. This project showcases my skills in data analysis, Python programming, and data visualization.

## About AuRIS

AuRIS is a proof-of-concept tool developed to streamline audit processes by identifying potential risks in financial transaction datasets. It is tailored for environments with large-scale operations, offering a foundation that can be scaled with future enhancements like ERP integration or machine learning. This project reflects my ability to solve real-world problems with a creative and analytical approach.

- **Author**: Amrit Dhandharia
- **Created**: April, 2025


## Features

AuRIS provides a comprehensive set of features to identify and visualize audit risks:

### 1. Duplicate Transaction Detection
- **What It Does**: Identifies transactions with identical `vendor`, `amount`, and `date` (excluding `invoice_id`).
- **Use Case**: Detects double payments or data entry errors, a common issue in large datasets like financial records.
- **Output**: Flagged in `risks_report.csv` with `risk_type = 'Duplicate'`.

### 2. Anomaly Detection
- **What It Does**: Flags transactions exceeding the 90th percentile of `amount` values.
- **Use Case**: Highlights unusually high-value transactions that may indicate fraud or errors, critical for expense monitoring.
- **Output**: Flagged in `risks_report.csv` with `risk_type = 'Anomaly'`.

### 3. Missing Data Detection
- **What It Does**: Identifies rows with missing values in any column.
- **Use Case**: Ensures data integrity, essential for audit compliance across sectors like FMCG and hotels.
- **Output**: Flagged in `risks_report.csv` with `risk_type = 'Missing Data'`.

### 4. Vendor Frequency Analysis
- **What It Does**: Flags vendors with transaction counts above the 90th percentile.
- **Use Case**: Spots overactive vendors, potentially indicating kickback schemes or supply chain irregularities.
- **Output**: Flagged in `risks_report.csv` with `risk_type = 'High Frequency'`.

### 5. Amount Deviation Detection
- **What It Does**: Flags transactions where `amount` is less than 20% or more than 200% of a vendor's average.
- **Use Case**: Detects unusual payment patterns, such as discounts or overcharges, relevant for vendor audits.
- **Output**: Flagged in `risks_report.csv` with `risk_type = 'Amount Deviation'`.


## Visualizations
1. **Transaction Amount Distribution (Histogram)**
   - **What It Does**: Displays the frequency of transaction amounts.
   - **Use Case**: Helps auditors understand common payment ranges and spot outliers.
   - **Output**: Saved as `amount_distribution.png`.

2. **Vendor Transaction Frequency (Bar Chart)**
   - **What It Does**: Shows the number of transactions per vendor.
   - **Use Case**: Highlights vendor activity levels, aiding in supply chain analysis.
   - **Output**: Saved as `vendor_frequency.png`.

3. **Transaction Amounts Over Time (Scatter with Trend)**
   - **What It Does**: Plots individual transactions with a rolling mean trend line.
   - **Use Case**: Reveals time-based patterns or spikes, useful for seasonal trend analysis.
   - **Output**: Saved as `time_series.png`.

4. **Risk Type Distribution (Pie Chart)**
   - **What It Does**: Shows the proportion of each risk type.
   - **Use Case**: Provides a quick overview for management or audit prioritization.
   - **Output**: Saved as `risk_distribution.png`.

5. **Transaction Density by Vendor and Date (Heatmap)**
   - **What It Does**: Visualizes transaction density across vendors and dates.
   - **Use Case**: Identifies busy periods or vendor-specific activity patterns.
   - **Output**: Saved as `vendor_date_heatmap.png`.
---

## Requirements

- **Python**: 3.13 or later
- **Libraries**:
  - `pandas` (for data manipulation)
  - `matplotlib` (for basic visualizations)
  - `seaborn` (for heatmap)

## Installation

### Step 1: Clone the Repository
If you’re using GitHub (setup instructions below), clone the repo:
```bash
git clone https://github.com/yourusername/AuRIS.git
cd AuRIS
```
### Step 2: Set up Virtual Environment
Create and activate virtual environment:
```bash
python3.13 -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate
``` 
### Step 3: Install Dependencies
Install required libraries:
```bash
pip install pandas matplotlib seaborn
```
### Step 4: Prepare Data
Place your transaction data in a CSV file named transactions.csv in the project directory. The expected columns are:
- invoice_id (unique identifier)
- vendor (string)
- amount (numeric)
- date (string, e.g., 2025-04-01)
- description (string, optional)

Example transactions.csv:
```text
invoice_id,vendor,amount,date,description
200,ABC Corp,1000,2025-04-01,Goods Purchase
201,XYZ Ltd,1001,2025-04-02,Services
...
```

## Usage
### Step 1: Run the Script
Activate the virtual environment and run the script:
```bash
source venv/bin/activate # On Windows: venv\Scripts\activate
python3.13 audit_risk.py
```
### Step 2: Review Outputs
- **Console Output**: Displays detected risks and confirmation of saved files.
- **Files Generated**:
    - `risks_report.csv`: Consolidated report of all flagged risks.
    - `amount_distribution.png`: Histogram of transaction amounts.
    - `vendor_frequency.png`: Bar chart of vendor transaction counts.
    - `time_series.png`: Scatter plot with trend line of amounts over time.
    - `risk_distribution.png`: Pie chart of risk type distribution.
    - `vendor_date_heatmap.png`: Heatmap of transaction density.

## Screenshots
- **Sample Input Data**
![image](https://github.com/user-attachments/assets/061d9b0f-93c6-4516-815a-e6e1c05c86e9) <br/>
- **Console Output** <br/>
![image](https://github.com/user-attachments/assets/ac5e0931-a83a-4641-ab9a-450a6f478232)
![image](https://github.com/user-attachments/assets/1ab9b8f4-fe8b-4595-a272-53034c15f0ec) <br/>
- **Output Report Sample**
![Screenshot from 2025-04-13 16-14-07](https://github.com/user-attachments/assets/36d20215-9fca-4af1-987c-b29a2c12b45d)
![Screenshot from 2025-04-13 16-15-40](https://github.com/user-attachments/assets/ef11332b-b319-45ba-9eeb-d0fa844db3e6)
- **Transaction Amount Distribution**
![Screenshot from 2025-04-13 16-08-48](https://github.com/user-attachments/assets/745d0da7-0145-4913-9681-7f7b3e629b93)
- **Vendor Transaction Frequency**
![Screenshot from 2025-04-13 16-09-29](https://github.com/user-attachments/assets/0dead59a-a04e-432f-b60b-4628d19e07e0)
- **Transaction Amounts Over Time**
![Screenshot from 2025-04-13 16-10-07](https://github.com/user-attachments/assets/5c396125-2f33-43c7-b015-1c4762c6bd98)
- **Risk Type Distribution**
![Screenshot from 2025-04-13 16-10-46](https://github.com/user-attachments/assets/57847afc-0287-4771-81c5-084fdbbe7758)
- **Transaction Density by Vendor and Date**
![Screenshot from 2025-04-13 16-11-35](https://github.com/user-attachments/assets/07b0a68c-d301-4e60-b758-fcad7fb1c6fe)
- **Before-and-After Comparison**
![image](https://github.com/user-attachments/assets/8e7cddbe-4d50-4c51-8fe3-a58d1fa5ee6f)
![image](https://github.com/user-attachments/assets/6d5193c7-c2ac-4ce7-ad5d-a7cac976a79e)
![image](https://github.com/user-attachments/assets/8eca3169-c47b-47cb-ba6c-936b1dd21b17)


## Future Improvements
- **Scalability**: Test and optimize for 10,000+ to 1,000,000+ rows to match real world data volume.
- **Advanced Features**: Add fraud pattern detection or ERP integration. Include relevant analysis of **Image** and **Video** data
- **User Interface**: Develop a GUI for non-technical users.
