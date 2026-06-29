"""AuRIS Streamlit dashboard for interactive audit risk analysis."""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auris.audit_risk import (
    check_amount_deviation,
    check_anomalies,
    check_duplicates,
    check_missing,
    check_vendor_frequency,
)
from auris.config import RiskConfig
from auris.summarize import summarize_risks

DEFAULT_CSV = PROJECT_ROOT / "data" / "transactions.csv"

st.set_page_config(page_title="AuRIS Dashboard", page_icon=":mag:", layout="wide")
st.title("AuRIS, Audit Risk Identification System")
st.markdown("Upload a transaction CSV to identify financial risks interactively.")

# Sidebar: upload + tunable thresholds (wired to RiskConfig).
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload transactions CSV", type=["csv"])

    st.subheader("Risk thresholds")
    anomaly_percentile = st.slider("Anomaly percentile threshold", 80, 99, 90)
    freq_percentile = st.slider("Vendor frequency percentile", 80, 99, 90)
    deviation_low = st.slider("Amount deviation low multiplier", 0.0, 1.0, 0.2, step=0.05)
    deviation_high = st.slider("Amount deviation high multiplier", 1.0, 5.0, 2.0, step=0.1)

config = RiskConfig(
    anomaly_quantile=anomaly_percentile / 100.0,
    vendor_frequency_quantile=freq_percentile / 100.0,
    deviation_low_multiplier=deviation_low,
    deviation_high_multiplier=deviation_high,
)

# Load data.
if uploaded_file is not None:
    data = pd.read_csv(uploaded_file)
else:
    try:
        data = pd.read_csv(DEFAULT_CSV)
        st.info(f"Using default `{DEFAULT_CSV.relative_to(PROJECT_ROOT)}`. Upload your own CSV in the sidebar.")
    except FileNotFoundError:
        st.warning("No data found. Please upload a transactions CSV file.")
        st.stop()

# Data preview.
st.subheader("Data Preview")
col1, col2, col3 = st.columns(3)
col1.metric("Total Transactions", len(data))
col2.metric("Unique Vendors", data["vendor"].nunique())
col3.metric("Date Range", f"{data['date'].min()} to {data['date'].max()}")
st.dataframe(data.head(20), use_container_width=True)

# Run risk checks, threading the RiskConfig built from sidebar sliders.
st.subheader("Risk Analysis")

duplicates = check_duplicates(data)
anomalies = check_anomalies(data, config)
missing = check_missing(data)
frequent_vendors = check_vendor_frequency(data, config)
amount_deviations = check_amount_deviation(data, config)

report = pd.concat(
    [duplicates, anomalies, missing, frequent_vendors, amount_deviations],
    ignore_index=True,
)

# Per-check summary metrics.
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

# AI-generated executive summary (opt-in, requires GROQ_API_KEY).
st.subheader("AI Executive Summary")
st.caption(
    "Generate a CFO-readable Markdown summary of the flagged risks using Llama 3.3 70B via Groq. "
    "Requires GROQ_API_KEY in the environment. Groq's free tier (14,400 requests/day, no credit card) "
    "makes typical development and demo usage cost nothing."
)
if st.button("Generate AI Summary"):
    with st.spinner("Asking Llama to summarise the risks..."):
        try:
            summary_md = summarize_risks(report, config)
            st.session_state["risk_summary_md"] = summary_md
        except RuntimeError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Failed to generate summary: {exc}")
if "risk_summary_md" in st.session_state:
    st.markdown(st.session_state["risk_summary_md"])
    st.download_button(
        "Download summary as Markdown",
        st.session_state["risk_summary_md"],
        "risk_summary.md",
        "text/markdown",
    )

# Filterable report table with CSV download.
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

# Visualizations.
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
