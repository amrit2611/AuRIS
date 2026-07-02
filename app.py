"""AuRIS Streamlit dashboard for interactive audit risk analysis.

Layout:
    - Sidebar (collapsed by default): risk-threshold sliders.
    - Main area top: prominent upload zone + "Try example" buttons.
    - Pipeline status: `st.status()` streams stage-by-stage progress.
    - Tabbed results: Overview | Findings | AI Summary.
      Overview holds a grid of chart thumbnails, each click opens a
      modal dialog with the full-size chart.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parent

from auris.audit_risk import (
    check_amount_deviation,
    check_anomalies,
    check_duplicates,
    check_missing,
    check_vendor_frequency,
)
from auris.config import RiskConfig
from auris.schema import REQUIRED_FIELDS, apply_mapping, detect_columns
from auris.summarize import summarize_risks

DEFAULT_CSV = PROJECT_ROOT / "data" / "transactions.csv"
NASA_CSV = PROJECT_ROOT / "data" / "usaspending_sample.csv"

st.set_page_config(
    page_title="AuRIS - Audit Risk Identification System",
    page_icon=":mag:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Lightweight styling: prominent upload target, tighter metric cards, taller tabs.
st.markdown(
    """
    <style>
      div[data-testid="stFileUploader"] section {
          border: 2px dashed rgba(255, 255, 255, 0.25);
          padding: 1.5rem;
          border-radius: 12px;
      }
      div[data-testid="stMetric"] {
          background: rgba(255, 255, 255, 0.04);
          padding: 0.75rem 1rem;
          border-radius: 10px;
      }
      button[role="tab"] {
          padding: 0.6rem 1.2rem !important;
          font-size: 1rem !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar: risk thresholds only (post-upload tuning knobs).
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Risk Thresholds")
    st.caption("Tune the sensitivity of each statistical check.")
    anomaly_percentile = st.slider("Anomaly percentile", 80, 99, 90, help="Amounts above this percentile are flagged.")
    freq_percentile = st.slider("Vendor frequency percentile", 80, 99, 90, help="Vendors above this percentile of transaction counts are flagged.")
    deviation_low = st.slider("Amount deviation low", 0.0, 1.0, 0.2, step=0.05, help="Rows below this multiplier of a vendor's mean are flagged.")
    deviation_high = st.slider("Amount deviation high", 1.0, 5.0, 2.0, step=0.1, help="Rows above this multiplier of a vendor's mean are flagged.")
    st.divider()
    st.caption("Built with Streamlit, Groq, Llama 3.3 70B. [github.com/amrit2611/AuRIS](https://github.com/amrit2611/AuRIS)")

config = RiskConfig(
    anomaly_quantile=anomaly_percentile / 100.0,
    vendor_frequency_quantile=freq_percentile / 100.0,
    deviation_low_multiplier=deviation_low,
    deviation_high_multiplier=deviation_high,
)

# ---------------------------------------------------------------------------
# Header + upload hero.
# ---------------------------------------------------------------------------
st.title(":mag: AuRIS - Audit Risk Identification System")
st.markdown(
    "Upload any transactions CSV. AuRIS runs six risk checks, uses an LLM to figure out your column mapping, "
    "and writes a CFO-readable executive summary. **Demo tool: do not upload sensitive or production data.**"
)

col_upload, col_examples = st.columns([2, 1])
with col_upload:
    uploaded_file = st.file_uploader(
        "**Drop a transaction CSV here or click to browse**",
        type=["csv"],
        help=(
            "Any CSV works. If your column names differ from AuRIS's schema "
            "(vendor / amount / date / invoice_id), an LLM will auto-map them; "
            "you confirm with a dropdown before analysis runs."
        ),
    )

with col_examples:
    st.markdown("**Or load a bundled example:**")
    example_choice = None
    if st.button(":test_tube: Synthetic 10K rows", use_container_width=True, help="AuRIS's built-in synthetic dataset (10,200 rows, 30 vendors)."):
        example_choice = "synthetic"
    if st.button(":rocket: Real NASA FY2024 contracts", use_container_width=True, help="5,254 rows of real US federal contract awards from usaspending.gov."):
        example_choice = "nasa"

# Reset stale AI-summary state when a new file loads.
if example_choice:
    st.session_state["_active_source"] = f"example::{example_choice}"
    st.session_state.pop("risk_summary_md", None)
elif uploaded_file is not None:
    st.session_state["_active_source"] = f"upload::{uploaded_file.name}::{uploaded_file.size}"

active_source = st.session_state.get("_active_source")
if not active_source:
    st.info("Waiting for a CSV. Upload above or click one of the example buttons.")
    st.stop()

# ---------------------------------------------------------------------------
# Pipeline: st.status streams each stage.
# ---------------------------------------------------------------------------
with st.status("Analysing your CSV...", expanded=True) as status:
    st.write(":inbox_tray: Loading data...")
    if active_source.startswith("example::synthetic"):
        data = pd.read_csv(DEFAULT_CSV)
        source_label = f"synthetic dataset ({DEFAULT_CSV.name})"
    elif active_source.startswith("example::nasa"):
        data = pd.read_csv(NASA_CSV)
        source_label = f"NASA FY2024 real contracts ({NASA_CSV.name})"
    else:
        data = pd.read_csv(uploaded_file)
        source_label = f"your upload ({uploaded_file.name})"
    st.write(f":white_check_mark: Loaded {len(data):,} rows, {data.shape[1]} columns from {source_label}.")

    already_mapped = set(REQUIRED_FIELDS).issubset(data.columns)
    mapping_error = None
    if already_mapped:
        st.write(":white_check_mark: CSV already uses AuRIS's schema, skipping column detection.")
    else:
        st.write(":robot_face: Detecting columns via Llama 3.3 70B...")
        if st.session_state.get("_mapping_source") != active_source:
            try:
                st.session_state["_detected_mapping"] = detect_columns(data, config)
                st.session_state["_mapping_source"] = active_source
                st.session_state["_mapping_error"] = None
            except Exception as exc:
                st.session_state["_detected_mapping"] = {k: None for k in REQUIRED_FIELDS}
                st.session_state["_mapping_source"] = active_source
                st.session_state["_mapping_error"] = str(exc)
        mapping_error = st.session_state.get("_mapping_error")
        if mapping_error:
            st.write(f":warning: Auto-detection failed: {mapping_error}. Map columns manually below.")
        else:
            detected = st.session_state["_detected_mapping"]
            preview = ", ".join(f"`{k}`->`{v}`" for k, v in detected.items() if v)
            st.write(f":white_check_mark: LLM suggested: {preview}. Confirm below.")

    st.write(":mag_right: Running six risk checks...")
    # column-mapping form (only if non-schema CSV).
    if not already_mapped:
        detected = st.session_state["_detected_mapping"]
        all_cols = list(data.columns)
        st.write("**Confirm column mapping** (AI guesses shown; change any dropdown to override):")
        map_cols = st.columns(4)
        user_mapping: dict[str, str | None] = {}
        for label, ui_col in zip(REQUIRED_FIELDS, map_cols):
            with ui_col:
                guess = detected.get(label)
                index = all_cols.index(guess) if guess in all_cols else 0
                picked = st.selectbox(
                    f"**{label}**",
                    options=all_cols,
                    index=index,
                    key=f"map_{label}_{active_source}",
                    help=f"AI guess: {guess if guess else 'no match'}",
                )
                user_mapping[label] = picked
        data = apply_mapping(data, user_mapping)

    duplicates = check_duplicates(data)
    st.write(f":white_check_mark: Duplicates: {len(duplicates):,} flagged.")
    anomalies = check_anomalies(data, config)
    st.write(f":white_check_mark: High-value anomalies: {len(anomalies):,} flagged.")
    missing = check_missing(data)
    st.write(f":white_check_mark: Missing data: {len(missing):,} flagged.")
    frequent_vendors = check_vendor_frequency(data, config)
    st.write(f":white_check_mark: High-frequency vendors: {len(frequent_vendors):,} flagged.")
    amount_deviations = check_amount_deviation(data, config)
    st.write(f":white_check_mark: Amount deviations: {len(amount_deviations):,} flagged.")

    report = pd.concat(
        [duplicates, anomalies, missing, frequent_vendors, amount_deviations],
        ignore_index=True,
    )
    status.update(
        label=f":white_check_mark: Analysis complete: {len(report):,} rows flagged across 5 checks",
        state="complete",
        expanded=False,
    )

# ---------------------------------------------------------------------------
# Top summary metrics (always visible, no scroll needed).
# ---------------------------------------------------------------------------
metric_cols = st.columns(4)
total_flagged_amount = float(report["amount"].dropna().sum()) if not report.empty else 0.0
metric_cols[0].metric("Total transactions", f"{len(data):,}")
metric_cols[1].metric("Rows flagged", f"{len(report):,}", delta=f"{(len(report) / max(len(data), 1)) * 100:.1f}% of dataset")
metric_cols[2].metric("Unique vendors", f"{data['vendor'].nunique():,}")
metric_cols[3].metric("Flagged $ exposure", f"${total_flagged_amount:,.0f}")

# ---------------------------------------------------------------------------
# Chart-modal helper. Streamlit's st.dialog creates a modal overlay so the
# user can view any chart full-size without leaving the page.
# ---------------------------------------------------------------------------
def _fig_amount_hist(data: pd.DataFrame, big: bool = False) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 5) if big else (5, 3))
    data["amount"].dropna().hist(bins=40, ax=ax, color="#4c9be8")
    ax.set_title("Transaction Amount Distribution")
    ax.set_xlabel("Amount")
    ax.set_ylabel("Frequency")
    plt.tight_layout()
    return fig


def _fig_vendor_bar(data: pd.DataFrame, big: bool = False) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 5) if big else (5, 3))
    data["vendor"].value_counts().head(20).plot(kind="bar", ax=ax, color="#e88b4c")
    ax.set_title("Top 20 Vendors by Transaction Count")
    ax.set_xlabel("Vendor")
    ax.set_ylabel("Count")
    plt.xticks(rotation=45, ha="right", fontsize=7 if not big else 9)
    plt.tight_layout()
    return fig


def _fig_time_series(data: pd.DataFrame, big: bool = False) -> plt.Figure:
    ts = data.dropna(subset=["amount"]).copy()
    ts["date"] = pd.to_datetime(ts["date"], errors="coerce")
    ts = ts.dropna(subset=["date"]).sort_values("date")
    fig, ax = plt.subplots(figsize=(10, 5) if big else (5, 3))
    ax.scatter(ts["date"], ts["amount"], alpha=0.3, s=8, color="#4c9be8")
    rolling = ts["amount"].rolling(window=50, min_periods=1).mean()
    ax.plot(ts["date"], rolling, color="#e64c4c", linewidth=1.6, label="Trend (50-pt rolling)")
    ax.set_title("Transaction Amounts Over Time")
    ax.set_xlabel("Date")
    ax.set_ylabel("Amount")
    ax.legend()
    plt.xticks(rotation=45, fontsize=7 if not big else 9)
    plt.tight_layout()
    return fig


def _fig_risk_pie(report: pd.DataFrame, big: bool = False) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 5) if big else (4, 3))
    if report.empty:
        ax.text(0.5, 0.5, "No risks detected", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return fig
    risk_counts = report["risk_type"].value_counts()
    ax.pie(risk_counts, labels=risk_counts.index, autopct="%1.1f%%", startangle=90,
           textprops={"fontsize": 7 if not big else 10})
    ax.set_title("Risk Type Distribution")
    ax.axis("equal")
    plt.tight_layout()
    return fig


def _fig_heatmap(data: pd.DataFrame, big: bool = False) -> plt.Figure:
    hm = data.copy()
    hm["date"] = pd.to_datetime(hm["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    hm = hm.dropna(subset=["date"])
    pivot = hm.pivot_table(values="amount", index="date", columns="vendor", aggfunc="count", fill_value=0)
    fig, ax = plt.subplots(figsize=(12, 6) if big else (5, 3))
    sns.heatmap(pivot, cmap="YlOrRd", ax=ax, cbar=big)
    ax.set_title("Transaction Density by Vendor and Date")
    plt.xticks(rotation=45, ha="right", fontsize=6 if not big else 8)
    plt.yticks(fontsize=6 if not big else 8)
    plt.tight_layout()
    return fig


CHART_BUILDERS = {
    "amount_hist": ("Amount Distribution", _fig_amount_hist, "data"),
    "vendor_bar": ("Top 20 Vendors", _fig_vendor_bar, "data"),
    "time_series": ("Amounts Over Time", _fig_time_series, "data"),
    "risk_pie": ("Risk Type Distribution", _fig_risk_pie, "report"),
    "heatmap": ("Vendor / Date Heatmap", _fig_heatmap, "data"),
}


@st.dialog(":bar_chart: Full-size chart view", width="large")
def show_chart_dialog(chart_id: str) -> None:
    """Render a chart at full size inside a modal overlay."""
    title, builder, source_key = CHART_BUILDERS[chart_id]
    source_df = report if source_key == "report" else data
    st.subheader(title)
    fig = builder(source_df, big=True)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

# ---------------------------------------------------------------------------
# Results: three tabs so nothing important is hidden behind a scroll.
# ---------------------------------------------------------------------------
tab_overview, tab_findings, tab_summary = st.tabs([
    ":chart_with_upwards_trend:  Overview",
    ":triangular_flag_on_post:  Findings",
    ":robot_face:  AI Summary",
])

with tab_overview:
    st.subheader("Per-check counts")
    per_check_cols = st.columns(5)
    per_check_data = [
        ("Duplicates", duplicates),
        ("Anomalies", anomalies),
        ("Missing Data", missing),
        ("High Frequency", frequent_vendors),
        ("Amount Deviation", amount_deviations),
    ]
    for col, (name, df) in zip(per_check_cols, per_check_data):
        col.metric(name, f"{len(df):,}")

    st.subheader("Visualisations")
    st.caption("Click :mag: on any chart to open it full size.")
    grid_rows = [list(CHART_BUILDERS.keys())[i:i + 3] for i in range(0, len(CHART_BUILDERS), 3)]
    for row in grid_rows:
        cols_row = st.columns(3)
        for cell_col, chart_id in zip(cols_row, row):
            with cell_col:
                title, builder, source_key = CHART_BUILDERS[chart_id]
                source_df = report if source_key == "report" else data
                fig = builder(source_df, big=False)
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
                st.button(
                    f":mag: Expand: {title}",
                    key=f"expand_{chart_id}",
                    use_container_width=True,
                    on_click=show_chart_dialog,
                    args=(chart_id,),
                )
        # Pad empty cells in the last row to keep the grid aligned.
        for cell_col in cols_row[len(row):]:
            with cell_col:
                st.empty()

with tab_findings:
    st.subheader("Flagged transactions")
    if report.empty:
        st.success("No risks detected under the current thresholds. Try lowering the sliders in the sidebar.")
    else:
        risk_filter = st.multiselect(
            "Filter by risk type",
            options=report["risk_type"].unique().tolist(),
            default=report["risk_type"].unique().tolist(),
        )
        filtered = report[report["risk_type"].isin(risk_filter)]
        st.caption(f"Showing {len(filtered):,} of {len(report):,} flagged rows.")
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            ":arrow_down: Download filtered report as CSV",
            csv_bytes,
            "risks_report.csv",
            "text/csv",
            use_container_width=True,
        )

with tab_summary:
    st.subheader("AI-generated executive summary")
    st.caption(
        "Groq's free tier (14,400 requests/day, no credit card) generates a CFO-readable Markdown summary. "
        "Groups by risk type, quantifies dollar exposure, names specific vendors, ends with prioritised actions."
    )
    if st.button(":robot_face: Generate AI Summary", type="primary", use_container_width=True):
        with st.spinner("Asking Llama 3.3 70B to summarise the risks..."):
            try:
                st.session_state["risk_summary_md"] = summarize_risks(report, config)
            except RuntimeError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Failed to generate summary: {exc}")

    if "risk_summary_md" in st.session_state:
        st.divider()
        st.markdown(st.session_state["risk_summary_md"])
        st.download_button(
            ":arrow_down: Download summary as Markdown",
            st.session_state["risk_summary_md"],
            "risk_summary.md",
            "text/markdown",
            use_container_width=True,
        )
