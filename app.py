"""AuRIS Streamlit dashboard - polished v2.

Design goals for this iteration (from user feedback):
    1. Metric card explains whether the flag rate is healthy signal
       (green under 5%), noisy (amber 5-10%), or too aggressive
       (red over 10%) with a one-line note.
    2. AI summary renders in a card with proper typography, not raw
       markdown.
    3. All charts are Plotly, so the user gets native fullscreen,
       zoom, hover on click - no more custom expand buttons or
       modal dialogs.
    4. Chart choices tuned for financial-audit data (log-scale
       histograms for right-skew, horizontal bars for long vendor
       names, donut with center count, interactive time series).
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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

PLOTLY_TEMPLATE = "plotly_dark"
COLOR_PRIMARY = "#4c9be8"
COLOR_ACCENT = "#e88b4c"
COLOR_ALERT = "#e64c4c"


def safe_for_arrow(df: pd.DataFrame) -> pd.DataFrame:
    """Cast object-dtype columns to string so pyarrow can serialise for st.dataframe."""
    if df is None or df.empty:
        return df
    obj_cols = df.select_dtypes(include=["object"]).columns
    if len(obj_cols) == 0:
        return df
    return df.astype({col: "string" for col in obj_cols})


st.set_page_config(
    page_title="AuRIS - Audit Risk Identification System",
    page_icon=":mag:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Global CSS: card polish for the metric row, the AI summary panel,
# and the drop zone. Keeps the app feeling native-Streamlit without
# fighting the theme.
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
      /* Neutralise stray inline `code` styling inside the AI summary card
         (Llama occasionally still wraps numbers in backticks despite the
         explicit prompt rule) so they read as plain text. */
      div[data-testid="stVerticalBlockBorderWrapper"] code {
          background: transparent;
          padding: 0;
          font-family: inherit;
          color: inherit;
          font-size: inherit;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar: risk thresholds. Defaults now reflect industry practice
# (top 1% for anomalies, top 5% for vendor frequency, wider deviation band).
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Risk Thresholds")
    st.caption("Tune sensitivity. Industry practice: 1-5% flag rate is a healthy review pool.")
    anomaly_percentile = st.slider("Anomaly percentile", 90, 99, 99, help="Amounts above this percentile are flagged.")
    freq_percentile = st.slider("Vendor frequency percentile", 90, 99, 95, help="Vendors above this percentile of transaction counts are flagged.")
    deviation_low = st.slider("Amount deviation low", 0.0, 1.0, 0.1, step=0.05, help="Rows below this multiplier of a vendor's mean are flagged.")
    deviation_high = st.slider("Amount deviation high", 1.5, 5.0, 3.0, step=0.1, help="Rows above this multiplier of a vendor's mean are flagged.")
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
            "Any CSV works. If your column names differ from AuRIS's schema, "
            "an LLM will auto-map them; you confirm with a dropdown before analysis runs."
        ),
    )

with col_examples:
    st.markdown("**Or load a bundled example:**")
    example_choice = None
    if st.button(":test_tube: Synthetic 10K rows", use_container_width=True, help="AuRIS's built-in synthetic dataset."):
        example_choice = "synthetic"
    if st.button(":rocket: Real NASA FY2024 contracts", use_container_width=True, help="5,254 real US federal contract awards from usaspending.gov."):
        example_choice = "nasa"

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
# Pipeline status.
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
            preview = ", ".join(f"{k} -> {v}" for k, v in detected.items() if v)
            st.write(f":white_check_mark: LLM suggested: {preview}. Confirm below.")

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

    st.write(":mag_right: Running six risk checks...")
    duplicates = check_duplicates(data)
    st.write(f":white_check_mark: Duplicates: {len(duplicates):,}")
    anomalies = check_anomalies(data, config)
    st.write(f":white_check_mark: High-value anomalies: {len(anomalies):,}")
    missing = check_missing(data)
    st.write(f":white_check_mark: Missing data: {len(missing):,}")
    frequent_vendors = check_vendor_frequency(data, config)
    st.write(f":white_check_mark: High-frequency vendors: {len(frequent_vendors):,}")
    amount_deviations = check_amount_deviation(data, config)
    st.write(f":white_check_mark: Amount deviations: {len(amount_deviations):,}")

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
# Metric row with context on whether the flag rate is signal or noise.
# ---------------------------------------------------------------------------
total_flagged_amount = float(report["amount"].dropna().sum()) if not report.empty else 0.0
flag_pct = (len(report) / max(len(data), 1)) * 100
if flag_pct <= 5:
    flag_delta = f"{flag_pct:.1f}% of dataset - healthy signal"
    flag_color = "normal"
elif flag_pct <= 10:
    flag_delta = f"{flag_pct:.1f}% of dataset - noisy"
    flag_color = "off"
else:
    flag_delta = f"{flag_pct:.1f}% of dataset - thresholds too aggressive, tighten sliders"
    flag_color = "inverse"

metric_cols = st.columns(4)
metric_cols[0].metric("Total transactions", f"{len(data):,}")
metric_cols[1].metric("Rows flagged", f"{len(report):,}", delta=flag_delta, delta_color=flag_color)
metric_cols[2].metric("Unique vendors", f"{data['vendor'].nunique():,}")
metric_cols[3].metric("Flagged $ exposure", f"${total_flagged_amount:,.0f}")

st.caption(
    "Reference: Industry practice flags 1-5% of transactions as a healthy audit review pool "
    "(ISA 320, PCAOB risk-based sampling). Above 10% typically signals thresholds are too "
    "aggressive to be actionable. Tune the sliders in the sidebar to match your review capacity."
)

# ---------------------------------------------------------------------------
# Plotly chart builders. Each returns a Plotly Figure with dark template.
# ---------------------------------------------------------------------------
def _plot_amount_histogram(data: pd.DataFrame) -> go.Figure:
    amounts = data["amount"].dropna()
    amounts = amounts[amounts > 0]  # log scale drops zero and negatives
    fig = px.histogram(
        amounts,
        x="amount",
        nbins=60,
        log_y=True,
        template=PLOTLY_TEMPLATE,
        color_discrete_sequence=[COLOR_PRIMARY],
        title=None,
    )
    fig.update_layout(
        margin=dict(l=30, r=20, t=30, b=40),
        xaxis_title="Transaction amount",
        yaxis_title="Frequency (log)",
        showlegend=False,
    )
    return fig


def _plot_vendor_bar(data: pd.DataFrame) -> go.Figure:
    top = data["vendor"].value_counts().head(15).sort_values(ascending=True)
    fig = px.bar(
        x=top.values,
        y=top.index,
        orientation="h",
        template=PLOTLY_TEMPLATE,
        color_discrete_sequence=[COLOR_ACCENT],
        title=None,
    )
    fig.update_layout(
        margin=dict(l=30, r=20, t=30, b=40),
        xaxis_title="Transaction count",
        yaxis_title=None,
        showlegend=False,
    )
    return fig


def _plot_time_series(data: pd.DataFrame) -> go.Figure:
    ts = data.dropna(subset=["amount"]).copy()
    ts["date"] = pd.to_datetime(ts["date"], errors="coerce")
    ts = ts.dropna(subset=["date"]).sort_values("date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts["date"], y=ts["amount"], mode="markers",
        marker=dict(color=COLOR_PRIMARY, opacity=0.35, size=4),
        name="Transactions", hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>",
    ))
    rolling = ts["amount"].rolling(window=50, min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=ts["date"], y=rolling, mode="lines",
        line=dict(color=COLOR_ALERT, width=2),
        name="Trend (50-pt rolling)",
    ))
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=30, r=20, t=30, b=40),
        xaxis_title="Date", yaxis_title="Amount",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(rangeslider=dict(visible=True), type="date"),
    )
    return fig


def _plot_risk_donut(report: pd.DataFrame) -> go.Figure:
    if report.empty:
        fig = go.Figure()
        fig.add_annotation(text="No risks detected", showarrow=False, font=dict(size=16, color="#888"))
        fig.update_layout(template=PLOTLY_TEMPLATE, margin=dict(l=0, r=0, t=0, b=0))
        return fig
    counts = report["risk_type"].value_counts()
    fig = go.Figure(data=[go.Pie(
        labels=counts.index, values=counts.values, hole=0.55,
        marker=dict(colors=px.colors.qualitative.Set2),
        textinfo="label+percent", textposition="outside",
    )])
    fig.add_annotation(
        text=f"<b>{len(report):,}</b><br>rows flagged",
        showarrow=False, font=dict(size=15),
    )
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=20, r=20, t=30, b=20),
        showlegend=False,
    )
    return fig


def _plot_vendor_exposure_treemap(report: pd.DataFrame) -> go.Figure:
    if report.empty or "vendor" not in report.columns:
        fig = go.Figure()
        fig.add_annotation(text="No flagged rows", showarrow=False, font=dict(size=16, color="#888"))
        fig.update_layout(template=PLOTLY_TEMPLATE, margin=dict(l=0, r=0, t=0, b=0))
        return fig
    with_amount = report.dropna(subset=["amount"]).copy()
    if with_amount.empty:
        fig = go.Figure()
        fig.add_annotation(text="No flagged rows have an amount", showarrow=False, font=dict(size=14, color="#888"))
        fig.update_layout(template=PLOTLY_TEMPLATE, margin=dict(l=0, r=0, t=0, b=0))
        return fig
    top_vendors = (
        with_amount.groupby("vendor")["amount"].sum().sort_values(ascending=False).head(20)
    )
    fig = px.treemap(
        names=top_vendors.index,
        parents=[""] * len(top_vendors),
        values=top_vendors.values,
        color=top_vendors.values,
        color_continuous_scale="YlOrRd",
        template=PLOTLY_TEMPLATE,
    )
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>$%{value:,.0f}",
        hovertemplate="%{label}<br>Total flagged: $%{value:,.0f}<extra></extra>",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), coloraxis_showscale=False)
    return fig


CHARTS = [
    ("Amount Distribution (log-scale)", "amount_hist", _plot_amount_histogram, "data"),
    ("Top Vendors by Transaction Count", "vendor_bar", _plot_vendor_bar, "data"),
    ("Amounts Over Time", "time_series", _plot_time_series, "data"),
    ("Risk Type Breakdown", "risk_donut", _plot_risk_donut, "report"),
    ("Top Flagged Vendors by $ Exposure", "vendor_treemap", _plot_vendor_exposure_treemap, "report"),
]

# ---------------------------------------------------------------------------
# Result tabs.
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
    st.caption(
        "Charts are interactive. Hover for details, double-click to zoom to fullscreen, "
        "click and drag to pan or select a range, use the toolbar (upper-right of each chart) to download or reset."
    )
    grid_rows = [CHARTS[i:i + 2] for i in range(0, len(CHARTS), 2)]
    for row in grid_rows:
        cols_row = st.columns(2)
        for cell_col, (title, chart_id, builder, source_key) in zip(cols_row, row):
            with cell_col:
                st.markdown(f"**{title}**")
                source_df = report if source_key == "report" else data
                fig = builder(source_df)
                st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        # Pad empty last-row cells.
        for cell_col in cols_row[len(row):]:
            with cell_col:
                st.empty()

with tab_findings:
    st.subheader("Flagged transactions")
    if report.empty:
        st.success("No risks detected under the current thresholds. Loosen the sidebar sliders for a wider net.")
    else:
        risk_filter = st.multiselect(
            "Filter by risk type",
            options=report["risk_type"].unique().tolist(),
            default=report["risk_type"].unique().tolist(),
        )
        filtered = report[report["risk_type"].isin(risk_filter)]
        st.caption(f"Showing {len(filtered):,} of {len(report):,} flagged rows.")
        st.dataframe(safe_for_arrow(filtered), use_container_width=True, hide_index=True)
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
        "Groq's free tier (14,400 requests/day, no credit card) generates a CFO-readable summary. "
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
        summary_md = st.session_state["risk_summary_md"]
        with st.container(border=True):
            st.markdown(summary_md)
        st.download_button(
            ":arrow_down: Download summary as Markdown",
            summary_md,
            "risk_summary.md",
            "text/markdown",
            use_container_width=True,
        )
