"""AuRIS Streamlit Dashboard — interactive audit risk analysis."""
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from audit_risk import (
    check_duplicates,
    check_anomalies,
    check_missing,
    check_vendor_frequency,
    check_amount_deviation,
)

st.set_page_config(page_title="AuRIS Dashboard", page_icon="🔍", layout="wide")
st.title("AuRIS — Audit Risk Identification System")
st.markdown("Upload a transaction CSV to identify financial risks interactively.")

# --- Sidebar: file upload & settings ---
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload transactions CSV", type=["csv"])
    anomaly_percentile = st.slider("Anomaly percentile threshold", 80, 99, 90)
    freq_percentile = st.slider("Vendor frequency percentile", 80, 99, 90)

# --- Load data ---
if uploaded_file is not None:
    data = pd.read_csv(uploaded_file)
else:
    try:
        data = pd.read_csv("transactions.csv")
        st.info("Using default `transactions.csv`. Upload your own CSV in the sidebar.")
    except FileNotFoundError:
        st.warning("No data found. Please upload a transactions CSV file.")
        st.stop()

# --- Data preview ---
st.subheader("Data Preview")
col1, col2, col3 = st.columns(3)
col1.metric("Total Transactions", len(data))
col2.metric("Unique Vendors", data["vendor"].nunique())
col3.metric("Date Range", f"{data['date'].min()} to {data['date'].max()}")
st.dataframe(data.head(20), use_container_width=True)

# --- Run risk checks ---
st.subheader("Risk Analysis")

duplicates = check_duplicates(data)
anomalies = check_anomalies(data)
missing = check_missing(data)
frequent_vendors = check_vendor_frequency(data)
amount_deviations = check_amount_deviation(data)

report = pd.concat(
    [duplicates, anomalies, missing, frequent_vendors, amount_deviations],
    ignore_index=True,
)

# --- Summary metrics ---
risk_cols = st.columns(5)
checks = [
    ("Duplicates", duplicates),
    ("Anomalies", anomalies),
    ("Missing Data", missing),
    ("High Frequency", frequent_vendors),
    ("Amount Deviation", amount_deviations),
]
for col, (name, df) in zip(risk_cols, checks):
    col.metric(name, len(df))

# --- Risk report table ---
if not report.empty:
    st.subheader("Flagged Transactions")
    risk_filter = st.multiselect(
        "Filter by risk type",
        options=report["risk_type"].unique().tolist(),
        default=report["risk_type"].unique().tolist(),
    )
    filtered = report[report["risk_type"].isin(risk_filter)]
    st.dataframe(filtered, use_container_width=True)

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered report as CSV", csv, "risks_report.csv", "text/csv")
else:
    st.success("No risks detected!")

# --- Visualizations ---
st.subheader("Visualizations")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Amount Distribution",
    "Vendor Frequency",
    "Time Series",
    "Risk Distribution",
    "Vendor-Date Heatmap",
])

with tab1:
    fig, ax = plt.subplots(figsize=(8, 5))
    data["amount"].dropna().hist(bins=40, ax=ax)
    ax.set_title("Transaction Amount Distribution")
    ax.set_xlabel("Amount")
    ax.set_ylabel("Frequency")
    st.pyplot(fig)

with tab2:
    fig, ax = plt.subplots(figsize=(10, 5))
    data["vendor"].value_counts().head(20).plot(kind="bar", ax=ax)
    ax.set_title("Top 20 Vendors by Transaction Count")
    ax.set_xlabel("Vendor")
    ax.set_ylabel("Count")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig)

with tab3:
    fig, ax = plt.subplots(figsize=(10, 5))
    ts_data = data.dropna(subset=["amount"]).copy()
    ts_data["date"] = pd.to_datetime(ts_data["date"])
    ts_data = ts_data.sort_values("date")
    ax.scatter(ts_data["date"], ts_data["amount"], alpha=0.3, s=10)
    rolling = ts_data["amount"].rolling(window=50, min_periods=1).mean()
    ax.plot(ts_data["date"], rolling, color="red", linewidth=2, label="Trend (50-pt)")
    ax.set_title("Transaction Amounts Over Time")
    ax.set_xlabel("Date")
    ax.set_ylabel("Amount")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig)

with tab4:
    if not report.empty:
        fig, ax = plt.subplots(figsize=(7, 5))
        risk_counts = report["risk_type"].value_counts()
        ax.pie(risk_counts, labels=risk_counts.index, autopct="%1.1f%%", startangle=90)
        ax.set_title("Risk Type Distribution")
        ax.axis("equal")
        st.pyplot(fig)
    else:
        st.info("No risks to display.")

with tab5:
    heatmap_data = data.copy()
    heatmap_data["date"] = pd.to_datetime(heatmap_data["date"]).dt.strftime("%Y-%m-%d")
    pivot = heatmap_data.pivot_table(
        values="amount", index="date", columns="vendor", aggfunc="count", fill_value=0
    )
    fig, ax = plt.subplots(figsize=(12, max(6, len(pivot) * 0.15)))
    sns.heatmap(pivot, cmap="YlOrRd", ax=ax)
    ax.set_title("Transaction Density by Vendor and Date")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig)
