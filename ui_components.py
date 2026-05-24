"""UI helpers for FinGuide. Numbers always use native st.metric / st.columns."""

from __future__ import annotations

import streamlit as st

CHART_COLORS = ["#2563eb", "#f97316", "#16a34a", "#9333ea", "#0891b2", "#e11d48"]
BRAND_NAVY = "#111827"
BRAND_ACCENT = "#2563eb"
BRAND_ACCENT_HOVER = "#1d4ed8"
NAV_OPTIONS = ["Overview", "Spending", "Forecast", "Transactions", "Advisor"]

RISK_COLOR = {
    "Low Risk": "#16a34a",
    "Medium Risk": "#d97706",
    "High Risk": "#dc2626",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, .stApp {
            background: #f9fafb !important;
            font-family: 'Inter', system-ui, sans-serif;
        }
        .main .block-container {
            padding: 1.5rem 2.5rem 3rem;
            max-width: 1120px;
        }

        /* ── Sidebar ─────────────────────────────── */
        [data-testid="stSidebar"] { background: #111827 !important; }
        [data-testid="stSidebar"] .stCaption { color: #9ca3af !important; }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
            color: #e5e7eb !important;
        }
        [data-testid="stSidebar"] details summary,
        [data-testid="stSidebar"] details summary span,
        [data-testid="stSidebar"] details summary p {
            color: #e5e7eb !important;
        }
        [data-testid="stSidebar"] hr { border-color: #374151 !important; }
        [data-testid="stSidebar"] [data-testid="stRadio"] > div {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            color: #9ca3af !important;
            padding: 0.45rem 0.75rem !important;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
            background: rgba(255,255,255,0.07);
            color: #f3f4f6 !important;
        }

        /* ── File uploader (dark sidebar, cohesive) ── */
        [data-testid="stSidebar"] [data-testid="stFileUploader"] {
            background: rgba(255, 255, 255, 0.04) !important;
            border: 1px dashed #4b5563 !important;
            border-radius: 12px !important;
            padding: 0.65rem 0.55rem !important;
            margin-top: 0.35rem !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] > label {
            color: #f3f4f6 !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
            margin-bottom: 0.5rem !important;
            background: transparent !important;
            padding: 0 !important;
        }

        /* Uploaded file rows (section + FileUploaderFile for newer Streamlit) */
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
            background-color: #1f2937 !important;
            border: 1px solid #374151 !important;
            border-radius: 8px !important;
            margin-bottom: 0.45rem !important;
            padding: 0.15rem 0.25rem !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section p,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section div,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] p,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] div {
            color: #f9fafb !important;
            -webkit-text-fill-color: #f9fafb !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section small,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] small {
            color: #9ca3af !important;
            -webkit-text-fill-color: #9ca3af !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section button,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button {
            background: transparent !important;
            border: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section button span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section button svg,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button span,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button svg {
            color: #d1d5db !important;
            fill: #d1d5db !important;
        }

        /* Dropzone (browse / limits) */
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            background: transparent !important;
            border: none !important;
            padding: 0.35rem 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] p,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] div {
            color: #d1d5db !important;
            -webkit-text-fill-color: #d1d5db !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small {
            color: #9ca3af !important;
            -webkit-text-fill-color: #9ca3af !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
            background: rgba(37, 99, 235, 0.12) !important;
            border: 1px solid #3b82f6 !important;
            border-radius: 8px !important;
            color: #93c5fd !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button:hover {
            background: rgba(37, 99, 235, 0.22) !important;
            border-color: #60a5fa !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button p,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button span {
            color: #bfdbfe !important;
            -webkit-text-fill-color: #bfdbfe !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] svg {
            fill: #93c5fd !important;
            stroke: #93c5fd !important;
        }

        /* ── Metric cards ────────────────────────── */
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        }
        div[data-testid="stMetricLabel"] {
            color: #6b7280 !important;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        div[data-testid="stMetricValue"] {
            color: #111827 !important;
            font-size: 1.4rem !important;
            font-weight: 700;
        }
        div[data-testid="stMetricDelta"] { font-size: 0.82rem; }

        /* ── DataFrames ───────────────────────────── */
        div[data-testid="stDataFrame"] {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            overflow: hidden;
        }

        /* ── General text ─────────────────────────── */
        h1, h2, h3 { color: #111827 !important; font-weight: 700; }
        p, label { color: #374151; }
        .stCaption { color: #9ca3af !important; }
        .fg-page-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: #111827;
            margin: 0 0 0.15rem;
        }
        .fg-page-sub {
            font-size: 0.875rem;
            color: #6b7280;
            margin: 0 0 1.25rem;
        }
        /* Let Streamlit headings handle section titles (avoids overlap with charts) */
        [data-testid="stVerticalBlock"] h3 {
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            color: #111827 !important;
            margin: 0.75rem 0 0.35rem !important;
            padding: 0 !important;
        }
        .fg-badge {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-bottom: 0.85rem;
        }
        .fg-risk-card {
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1.15rem 1.3rem;
        }
        .fg-landing {
            max-width: 520px;
            margin: 4rem auto 2rem;
            text-align: center;
        }
        .fg-landing h2 {
            font-size: 2rem;
            font-weight: 700;
            color: #111827;
            margin: 0.5rem 0;
        }
        .fg-landing p { color: #6b7280; font-size: 1rem; line-height: 1.7; }
        .fg-chips {
            display: flex; flex-wrap: wrap; gap: 0.5rem;
            justify-content: center; margin-top: 1.5rem;
        }
        .fg-chip {
            background: #fff; border: 1px solid #e5e7eb;
            color: #374151; font-size: 0.8rem; font-weight: 500;
            padding: 0.3rem 0.8rem; border-radius: 999px;
        }
        #MainMenu, footer { visibility: hidden; }
        header[data-testid="stHeader"] { background: transparent !important; }

        /* PDF download — brand accent */
        .main .fg-pdf-download [data-testid="stDownloadButton"] button {
            background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.6rem 1.4rem !important;
            font-weight: 600 !important;
            font-size: 0.9rem !important;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35) !important;
        }
        .main .fg-pdf-download [data-testid="stDownloadButton"] button:hover {
            background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%) !important;
            color: #ffffff !important;
            border: none !important;
        }
        .main .fg-pdf-download [data-testid="stDownloadButton"] button p,
        .main .fg-pdf-download [data-testid="stDownloadButton"] button span {
            color: #ffffff !important;
        }
        .main .fg-pdf-download [data-testid="stDownloadButton"] {
            margin: 0.25rem 0 0.75rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def plotly_theme(fig, title: str | None = None, *, pie: bool = False):
    """Apply theme. Pie charts: no in-chart title (use st.subheader) to avoid clipping."""
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui", color="#6b7280", size=11),
        showlegend=True,
    )
    if pie:
        layout["margin"] = dict(l=48, r=48, t=36, b=100)
        layout["legend"] = dict(
            orientation="h",
            yanchor="top",
            y=-0.14,
            xanchor="center",
            x=0.5,
            font=dict(color="#374151", size=10),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e5e7eb",
            borderwidth=1,
        )
        layout["height"] = 440
    else:
        layout["colorway"] = CHART_COLORS
        layout["margin"] = dict(l=8, r=8, t=48 if title else 16, b=8)
        layout["legend"] = dict(font=dict(color="#374151"), bgcolor="rgba(0,0,0,0)")
        if title:
            layout["title"] = dict(
                text=title,
                font=dict(size=14, color="#111827"),
                y=0.98,
                yanchor="top",
            )

    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="#f3f4f6", tickfont=dict(color="#9ca3af"), linecolor="#e5e7eb")
    fig.update_yaxes(gridcolor="#f3f4f6", tickfont=dict(color="#9ca3af"), linecolor="#e5e7eb")
    return fig


def spending_pie_chart(cat_summary):
    """
    Pie from category table: every category with spend > 0, legend matches slices only.
    Title belongs in Streamlit (section_heading), not inside Plotly.
    """
    import plotly.express as px

    if cat_summary is None or cat_summary.empty:
        return None

    chart_df = cat_summary[cat_summary["spend_amount"] > 0].copy()
    chart_df = chart_df[~chart_df["predicted_category"].isin(["Transfer"])]
    if chart_df.empty:
        return None

    chart_df = chart_df.sort_values("spend_amount", ascending=False)
    cats = chart_df["predicted_category"].tolist()
    color_map = {c: CHART_COLORS[i % len(CHART_COLORS)] for i, c in enumerate(cats)}

    fig = px.pie(
        chart_df,
        names="predicted_category",
        values="spend_amount",
        hole=0.42,
        color="predicted_category",
        color_discrete_map=color_map,
        category_orders={"predicted_category": cats},
    )
    fig.update_traces(
        textposition="outside",
        textinfo="percent",
        textfont_size=10,
        outsidetextfont=dict(size=10, color="#374151"),
        marker=dict(line=dict(color="#ffffff", width=2)),
        pull=[0.015] * len(chart_df),
        hovertemplate="%{label}<br>₹%{value:,.0f} (%{percent})<br>Rows: %{customdata}<extra></extra>",
        customdata=chart_df["txn_count"],
    )
    plotly_theme(fig, pie=True)
    return fig


def render_pdf_download_button(
    label: str,
    data: bytes,
    file_name: str,
    mime: str = "application/pdf",
    help_text: str = "",
):
    """Download button styled with FinGuide accent blue."""
    st.markdown('<div class="fg-pdf-download">', unsafe_allow_html=True)
    st.download_button(
        label=label,
        data=data,
        file_name=file_name,
        mime=mime,
        help=help_text or None,
        type="primary",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def fmt_inr(val: float) -> str:
    return f"₹{val:,.0f}"


def render_landing():
    st.markdown(
        """
        <div class="fg-landing">
            <div class="fg-chips">
                <span class="fg-chip">HDFC</span>
                <span class="fg-chip">SBI</span>
                <span class="fg-chip">ICICI</span>
                <span class="fg-chip">Axis</span>
                <span class="fg-chip">Kotak</span>
            </div>
            <h2>Your finances, decoded</h2>
            <p>Upload a bank statement PDF or CSV from the sidebar. FinGuide categorizes every transaction, forecasts next-month cash flow, scores your risk, and answers questions.</p>
            <p style="font-size:0.85rem;color:#6b7280;margin-top:1rem;">
                Uploads are processed in your Streamlit session (not saved to disk). Advisor chat only sends anonymized totals to Groq — never your full statement.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_main_header(txn_count: int, file_names: list[str]):
    names = ", ".join(file_names[:3])
    if len(file_names) > 3:
        names += f" +{len(file_names) - 3} more"
    st.markdown(f'<p class="fg-page-title">{txn_count:,} transactions parsed</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="fg-page-sub">{names}</p>', unsafe_allow_html=True)


def render_stat_row(
    income: float,
    expense: float,
    net: float,
    txns: int,
    transfer_out: float = 0.0,
    transfer_in: float = 0.0,
):
    """Four metric cards using native st.metric (always renders numbers correctly)."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Income",
        fmt_inr(income),
        help="All credits, including IMPS/UPI transfer-ins",
    )
    c2.metric(
        "Expenses (excl. transfer out)",
        fmt_inr(expense),
        help="Spending only — outbound transfers removed",
    )
    c3.metric(
        "Net cash flow",
        fmt_inr(net),
        delta=f"{'▲' if net >= 0 else '▼'} {fmt_inr(abs(net))}",
        delta_color="normal" if net >= 0 else "inverse",
    )
    c4.metric(
        "Transfers out (excl.)",
        fmt_inr(transfer_out),
        help=f"Transfer credits in income: {fmt_inr(transfer_in)}" if transfer_in else None,
    )


def render_risk_block(level: str, score: int, reasons: list[str]):
    color = RISK_COLOR.get(level, "#374151")
    badge_bg = {"Low Risk": "#dcfce7", "Medium Risk": "#fef9c3", "High Risk": "#fee2e2"}.get(level, "#f3f4f6")
    reasons_html = "".join(
        f'<li style="color:#6b7280;margin:0.4rem 0;font-size:0.875rem;">{r}</li>'
        for r in reasons
    )
    if not reasons_html:
        reasons_html = '<li style="color:#9ca3af;font-size:0.875rem;">No major flags found.</li>'
    st.markdown(
        f"""
        <div class="fg-risk-card">
            <span class="fg-badge" style="background:{badge_bg};color:{color};">{level}</span>
            <div style="font-size:2rem;font-weight:700;color:{color};line-height:1;">{score}<span style="font-size:1rem;font-weight:400;color:#9ca3af;"> / 100</span></div>
            <ul style="margin:0.75rem 0 0;padding-left:1.1rem;">{reasons_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_heading(title: str, subtitle: str = ""):
    """Native Streamlit headings — avoids HTML/chart overlap and 'undefined' glitches."""
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)
