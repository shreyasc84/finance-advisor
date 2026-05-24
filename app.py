import io
import os
import re
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
import pdfplumber
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from parsers.bank_parsers import parse_pdf_transactions as _parse_bank_pdf
from pdf_export import build_summary_pdf
from privacy_utils import (
    PRIVACY_SIDEBAR_NOTE,
    build_advisor_context,
    redact_narration,
    uploads_fingerprint,
)
from ui_components import (
    NAV_OPTIONS,
    inject_styles,
    plotly_theme,
    render_landing,
    render_main_header,
    render_risk_block,
    render_pdf_download_button,
    render_stat_row,
    section_heading,
    spending_pie_chart,
)

try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
except Exception:  # pragma: no cover
    ChatGroq = None
    HumanMessage = SystemMessage = AIMessage = None
    ChatPromptTemplate = MessagesPlaceholder = None


st.set_page_config(page_title="FinGuide", layout="wide", initial_sidebar_state="expanded")
load_dotenv()


MODELS_DIR = "models"
CLASSIFIER_PATH = os.path.join(MODELS_DIR, "transaction_classifier.pkl")
REGRESSOR_PATH = os.path.join(MODELS_DIR, "cashflow_forecasters.pkl")

DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
AMOUNT_RE = re.compile(r"(?:INR|Rs\.?|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)", re.IGNORECASE)
CR_DR_RE = re.compile(r"\b(CR|CREDIT|DR|DEBIT)\b", re.IGNORECASE)
REF_RE = re.compile(r"\|\s*Ref:[a-z0-9]+", re.IGNORECASE)
AMT_TEXT_RE = re.compile(r"\|\s*Amount:.*$", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = REF_RE.sub("", text)
    text = AMT_TEXT_RE.sub("", text)
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_merchant_text(text: str) -> str:
    left = text.split("|")[0]
    left = re.sub(r"[^a-zA-Z\s]", " ", left)
    return re.sub(r"\s+", " ", left).strip().lower()


def parse_date_from_text(text: str):
    m = DATE_RE.search(text)
    if not m:
        return pd.NaT
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return pd.to_datetime(datetime.strptime(m.group(1), fmt).date())
        except ValueError:
            continue
    return pd.NaT


def parse_statement_date(text: str):
    if text is None:
        return pd.NaT
    text = str(text).strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return pd.to_datetime(datetime.strptime(text, fmt).date())
        except ValueError:
            continue
    return parse_date_from_text(text)


def parse_amount_cell(val):
    if val is None:
        return np.nan
    s = str(val).strip()
    if not s or s == "-":
        return np.nan
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.]", "", s)
    if not s:
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def extract_amount(text: str):
    m = AMOUNT_RE.search(text)
    if not m:
        return np.nan
    return float(m.group(1).replace(",", ""))


def infer_txn_type(text: str):
    m = CR_DR_RE.search(text)
    if m:
        token = m.group(1).upper()
        if token in {"CR", "CREDIT"}:
            return "Income"
        return "Expense"
    if any(k in text.lower() for k in ["salary", "refund", "interest credit", "cashback"]):
        return "Income"
    return "Expense"


def parse_pdf_transactions(pdf_bytes: bytes) -> pd.DataFrame:
    return _parse_bank_pdf(pdf_bytes)


def parse_csv_transactions(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes))
    if "Transaction_Text" in df.columns:
        out = pd.DataFrame()
        out["raw_line"] = df["Transaction_Text"].astype(str)
        out["amount"] = out["raw_line"].apply(extract_amount)
        out["date"] = out["raw_line"].apply(parse_date_from_text)
        out["txn_type"] = out["raw_line"].apply(infer_txn_type)
        return out
    raise ValueError("CSV must include Transaction_Text column for this app.")


def build_classifier_features(txn_df: pd.DataFrame) -> pd.DataFrame:
    feat = txn_df.copy()
    feat["clean_text"] = feat["raw_line"].apply(clean_text)
    feat["merchant_text"] = feat["raw_line"].apply(extract_merchant_text)
    feat["amount_log"] = np.log1p(feat["amount"])
    feat["text_len"] = feat["clean_text"].str.len().astype(float)
    return feat


def infer_transfer_like(raw_line: str, merchant_text: str) -> bool:
    """
    Mark P2P / self / rail transfers. Overrides the spend classifier when matched.

    The model only knows: EMI, Food, Investment, Shopping, Travel.
    IMPS/NEFT/RTGS peer lines (e.g. IMPS- -NAME-KKBK-XXXX) rarely contain the word
    'transfer', so we key off rail keywords and bank-code fragments.
    """
    s = f"{raw_line} {merchant_text}".lower()
    compact = re.sub(r"\s+", "", s)

    # UPI to a person (HDFC/SBI: UPI/MR NAME, …)
    if re.search(r"upi/(mr|mrs|ms|miss)\s", s):
        return True

    # UPI / IMPS / NEFT with payee + bank code (IMPS- -SHREYASC-KKBK-XXXX, etc.)
    if re.search(r"\b(upi|imps|neft|rtgs)\b", s) and re.search(
        r"-[a-z]{4,11}(?:-|\||$|\s|\d)", s
    ):
        return True

    # Self transfers between own accounts
    if re.search(r"\b(self\s+transfer|transfer\s+to\s+self|to\s+self\b|from\s+self\b)\b", s):
        return True

    # Rail keywords (Indian statements: IMPS-, NEFT CR, RTGS, internal FT)
    if re.search(r"\b(imps|neft|rtgs|ift)\b", s):
        return True

    # Inter-bank fund transfer narrations (HDFC IBFUNDSTRANSFERDR, etc.)
    if "ibfundstransfer" in compact or re.search(r"\bfunds?\s*transfer\b", s):
        return True

    # e-Rupee wallet moves
    if "erupee" in s or "e-rupee" in s:
        return True

    return False


def build_risk_category_shares(expense_df: pd.DataFrame, exclude: set[str]) -> dict:
    """Category fractions for risk rules — same denominator as expense_total (excl. transfers)."""
    spend = expense_df[~expense_df["predicted_category"].isin(exclude)]
    denom = spend["amount"].sum()
    if denom <= 0:
        return {}
    return (spend.groupby("predicted_category")["amount"].sum() / denom).to_dict()


def risk_profile(
    expense_total: float,
    income_total: float,
    category_share: dict,
    forecast_net,
    transfer_spend: float = 0.0,
):
    """
    Rule-based risk score (0–100) from statement aggregates.

    Income counts all credits. Expenses exclude outbound Transfer rows only.
    category_share uses the same expense base as expense_total.
    """
    score = 0
    reasons = []

    savings_rate = (
        (income_total - expense_total) / income_total if income_total > 0 else None
    )

    if income_total <= 0:
        score += 35
        reasons.append("No reliable income credits in this period.")
    elif savings_rate is not None:
        pct = savings_rate * 100
        if savings_rate < 0:
            score += 30
            reasons.append(f"Expenses exceed income (savings rate {pct:.1f}%).")
        elif savings_rate < 0.15:
            score += 15
            reasons.append(f"Low savings rate ({pct:.1f}% — target ≥ 15%).")

    emi_share = category_share.get("EMI", 0)
    if emi_share > 0.30:
        score += 25
        reasons.append(f"High EMI share ({emi_share * 100:.1f}% of counted expenses).")
    elif emi_share > 0.20:
        score += 12
        reasons.append(f"Moderate EMI share ({emi_share * 100:.1f}% of counted expenses).")

    discretionary = category_share.get("Shopping", 0) + category_share.get("Travel", 0)
    if discretionary > 0.50:
        score += 20
        reasons.append(
            f"High discretionary spend ({discretionary * 100:.1f}% — Shopping + Travel)."
        )
    elif discretionary > 0.35:
        score += 10
        reasons.append(
            f"Moderate discretionary spend ({discretionary * 100:.1f}% — Shopping + Travel)."
        )

    uncl_share = category_share.get("Unclassified", 0)
    if uncl_share > 0.25:
        score += 10
        reasons.append(
            f"Many expenses unclassified ({uncl_share * 100:.1f}% of counted spend)."
        )

    outflow_base = expense_total + transfer_spend
    if transfer_spend > 0 and outflow_base > 0:
        xfer_pct = transfer_spend / outflow_base * 100
        if xfer_pct >= 50:
            score += 8
            reasons.append(
                f"Most outflows are transfers ({xfer_pct:.1f}% of transfers + counted expenses)."
            )

    if forecast_net is not None and forecast_net < 0:
        score += 20
        reasons.append(
            f"Forecast next-month net is negative (₹{forecast_net:,.0f})."
        )

    score = min(100, score)
    if score >= 55:
        level = "High Risk"
    elif score >= 30:
        level = "Medium Risk"
    else:
        level = "Low Risk"
    return level, score, reasons


def build_forecast_features(monthly_df: pd.DataFrame, payload: dict):
    n_lags = int(payload.get("n_lags", 5))
    smooth_window = int(payload.get("smooth_window", 10))
    if len(monthly_df) < n_lags + 1:
        return None

    frame = monthly_df.copy().sort_values("YearMonth").reset_index(drop=True)
    frame["Expense_Smoothed"] = frame["Expense_Amount"].rolling(window=smooth_window, min_periods=1).mean()
    frame["Income_Smoothed"] = frame["Income_Amount"].rolling(window=smooth_window, min_periods=1).mean()
    frame["Net_Smoothed"] = frame["Net_Cash_Flow"].rolling(window=smooth_window, min_periods=1).mean()

    next_idx = len(frame)
    next_month = (frame["YearMonth"].iloc[-1] + 1).month
    base = {
        "time_step": float(next_idx),
        "month_sin": float(np.sin(2 * np.pi * next_month / 12)),
        "month_cos": float(np.cos(2 * np.pi * next_month / 12)),
    }
    for lag in range(1, n_lags + 1):
        base[f"exp_lag_{lag}"] = float(frame["Expense_Smoothed"].iloc[-lag])
        base[f"inc_lag_{lag}"] = float(frame["Income_Smoothed"].iloc[-lag])
        base[f"net_lag_{lag}"] = float(frame["Net_Smoothed"].iloc[-lag])
    return base


ADVISOR_SYSTEM_PROMPT = """You are FinGuide — a friendly personal finance coach for someone in India.

You receive an anonymized summary (totals and categories only — no names, account numbers, or raw bank lines).
Talk like a helpful human, not a report generator.

Conversation style:
- Start with a short, direct answer to what they asked (1–2 sentences).
- Use "you" and "your". It's okay to say "looks like" or "I'd watch out for" when inferring.
- Use ₹ and round to whole rupees unless they ask for decimals.
- Keep most replies under 150 words unless they ask for a deep dive.
- Use short paragraphs or a few bullets — avoid long numbered reports unless they ask for a plan.
- If they say hi or ask something vague, greet them and offer 2–3 things you can help with based on their data.
- Reference specific numbers from the context (categories, net cash flow, risk score).
- One follow-up question at the end is fine ("Want me to break down Food spend?").

When they want a full plan, then give: quick diagnosis → 3 prioritized actions with ₹ where possible → one risk → 30-day checklist.

Never: guaranteed returns, illegal tax tricks, medical/legal advice.
If data is missing, say what you'd need — don't guess."""


inject_styles()

with st.sidebar:
    st.markdown(
        '<p style="font-family:Fraunces,serif;font-size:1.35rem;font-weight:700;margin:0 0 0.25rem;color:#f3f4f6;">FinGuide</p>',
        unsafe_allow_html=True,
    )
    st.caption("Runs on your bank statements")
    uploaded_files = st.file_uploader(
        "Statement (PDF or CSV)",
        type=["pdf", "csv"],
        accept_multiple_files=True,
        key="statement_uploader",
    )
    st.divider()
    section = st.radio("Navigate", NAV_OPTIONS, label_visibility="collapsed")
    st.divider()
    with st.expander("Privacy & data", expanded=False):
        st.markdown(PRIVACY_SIDEBAR_NOTE)

if not uploaded_files:
    render_landing()
    st.stop()

# Reset advisor chat when the user uploads different files (session-only data hygiene)
_upload_fp = uploads_fingerprint(uploaded_files)
if st.session_state.get("upload_fp") != _upload_fp:
    st.session_state.upload_fp = _upload_fp
    st.session_state.pop("advisor_messages", None)

all_txn = []
for uf in uploaded_files:
    name = uf.name.lower()
    try:
        if name.endswith(".pdf"):
            parsed = parse_pdf_transactions(uf.read())
        else:
            parsed = parse_csv_transactions(uf.read())
        parsed["source_file"] = uf.name
        all_txn.append(parsed)
    except Exception as e:
        st.warning(f"Could not parse `{uf.name}`: {e}")

if not all_txn:
    st.error("No parseable transactions found.")
    st.stop()

txn_df = pd.concat(all_txn, ignore_index=True)
if "amount" not in txn_df.columns:
    st.error("Parsed files did not contain detectable transaction amounts.")
    st.stop()

txn_df = txn_df.dropna(subset=["amount"]).copy()
if txn_df.empty:
    st.error("No valid transaction rows with amounts were detected after parsing.")
    st.stop()

txn_df["date"] = pd.to_datetime(txn_df["date"], errors="coerce")

# ── Classification ──────────────────────────────────────────────────────────
if not os.path.exists(CLASSIFIER_PATH):
    st.error(f"Missing classifier model: `{CLASSIFIER_PATH}`")
    st.stop()

classifier = joblib.load(CLASSIFIER_PATH)
feat_df = build_classifier_features(txn_df)

# Model expects these columns in current notebook pipeline
required_cols = ["clean_text", "merchant_text", "amount_log", "text_len"]
pred_labels = classifier.predict(feat_df[required_cols]).astype(object)

# Confidence-aware fallback:
# If model confidence is low (or transaction looks like person-to-person transfer),
# avoid forcing one of the 5 spend classes and tag as Transfer/Unclassified.
if hasattr(classifier, "predict_proba"):
    probs = classifier.predict_proba(feat_df[required_cols])
    max_conf = probs.max(axis=1)
    feat_df["pred_confidence"] = max_conf
else:
    feat_df["pred_confidence"] = np.nan

transfer_mask = feat_df.apply(lambda r: infer_transfer_like(str(r["raw_line"]), str(r["merchant_text"])), axis=1)
low_conf_mask = feat_df["pred_confidence"].fillna(1.0) < 0.60
pred_labels[transfer_mask.values] = "Transfer"
pred_labels[(~transfer_mask).values & low_conf_mask.values] = "Unclassified"
feat_df["predicted_category"] = pred_labels

show_cols = ["source_file", "date", "txn_type", "amount", "predicted_category", "raw_line"]
if "pred_confidence" in feat_df.columns:
    show_cols.insert(5, "pred_confidence")

# Focus classification on expenses
expense_df = feat_df[feat_df["txn_type"] == "Expense"].copy()
if expense_df.empty:
    expense_df = feat_df.copy()

cat_summary = (
    expense_df.groupby("predicted_category")
    .agg(spend_amount=("amount", "sum"), txn_count=("amount", "count"))
    .sort_values("spend_amount", ascending=False)
    .reset_index()
)
total_expense = cat_summary["spend_amount"].sum() if not cat_summary.empty else 0.0
cat_summary["share_pct"] = (
    (cat_summary["spend_amount"] / total_expense * 100).round(2) if total_expense > 0 else 0
)

forecast_expense = None
forecast_income = None
forecast_net = None
monthly = pd.DataFrame()

# Outbound transfers excluded from spend totals; inbound transfer credits stay in income
_excl = {"Transfer"}
income_total = feat_df.loc[feat_df["txn_type"] == "Income", "amount"].sum()
expense_total = feat_df.loc[
    (feat_df["txn_type"] == "Expense") & (~feat_df["predicted_category"].isin(_excl)),
    "amount",
].sum()
transfer_out_total = feat_df.loc[
    (feat_df["predicted_category"] == "Transfer") & (feat_df["txn_type"] == "Expense"),
    "amount",
].sum()
transfer_in_total = feat_df.loc[
    (feat_df["predicted_category"] == "Transfer") & (feat_df["txn_type"] == "Income"),
    "amount",
].sum()
net_total = income_total - expense_total

# Risk/health ratios: shares of counted expenses only (matches expense_total denominator)
share_map = build_risk_category_shares(expense_df, _excl)

forecast_note = None
if os.path.exists(REGRESSOR_PATH):
    reg_payload = joblib.load(REGRESSOR_PATH)
    txn_monthly = feat_df.copy()
    txn_monthly["YearMonth"] = txn_monthly["date"].dt.to_period("M")
    txn_monthly = txn_monthly.dropna(subset=["YearMonth"])
    monthly = (
        txn_monthly.groupby(["YearMonth", "txn_type"])["amount"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    if "Expense" not in monthly.columns:
        monthly["Expense"] = 0.0
    if "Income" not in monthly.columns:
        monthly["Income"] = 0.0
    monthly = monthly.rename(columns={"Expense": "Expense_Amount", "Income": "Income_Amount"})
    monthly["Net_Cash_Flow"] = monthly["Income_Amount"] - monthly["Expense_Amount"]
    monthly = monthly.sort_values("YearMonth")

    feature_dict = build_forecast_features(monthly, reg_payload)
    if feature_dict is None:
        forecast_note = "Need more months of data for a reliable forecast."
    else:
        exp_cols = reg_payload["features"]["expense"]
        inc_cols = reg_payload["features"]["income"]
        net_cols = reg_payload["features"]["net"]
        x_exp = pd.DataFrame([{k: feature_dict[k] for k in exp_cols}])
        x_inc = pd.DataFrame([{k: feature_dict[k] for k in inc_cols}])
        x_net = pd.DataFrame([{k: feature_dict[k] for k in net_cols}])
        forecast_expense = float(reg_payload["expense_model"].predict(x_exp)[0])
        forecast_income = float(reg_payload["income_model"].predict(x_inc)[0])
        forecast_net = float(reg_payload["net_model"].predict(x_net)[0])
else:
    forecast_note = "Forecast model not found. Train `expense_forecasting.ipynb` first."

level, score, reasons = risk_profile(
    expense_total, income_total, share_map, forecast_net, transfer_spend=transfer_out_total
)

file_names = [uf.name for uf in uploaded_files]
render_main_header(len(feat_df), file_names)
render_stat_row(
    income_total, expense_total, net_total, len(feat_df), transfer_out_total, transfer_in_total
)
st.caption(
    "Income includes all credits (including transfer-ins). Expenses exclude outbound transfers only. "
    "Risk score uses the same bases."
)

try:
    _pdf_bytes = build_summary_pdf(
        file_names=file_names,
        txn_count=len(feat_df),
        income_total=income_total,
        expense_total=expense_total,
        net_total=net_total,
        transfer_out=transfer_out_total,
        transfer_in=transfer_in_total,
        risk_level=level,
        risk_score=score,
        risk_reasons=reasons,
        cat_summary=cat_summary,
        forecast_expense=forecast_expense,
        forecast_income=forecast_income,
        forecast_net=forecast_net,
        forecast_note=forecast_note,
        monthly=monthly,
    )
    render_pdf_download_button(
        label="Download PDF report",
        data=_pdf_bytes,
        file_name="finguide_summary.pdf",
        mime="application/pdf",
        help_text="Summary, risk, category table, spending pie chart, and cash-flow chart",
    )
except Exception as _pdf_err:
    st.caption(f"PDF export unavailable: {_pdf_err}")

st.divider()

if section == "Overview":
    # ── Row 1: risk + pie chart ──────────────────────────────────────────────
    col_a, col_b = st.columns([1, 1], gap="large")
    with col_a:
        section_heading("Risk profile")
        render_risk_block(level, score, reasons)
    with col_b:
        if not cat_summary.empty:
            section_heading(
                "Spending by category",
                f"All {int(cat_summary['txn_count'].sum()):,} expense rows · amounts in ₹",
            )
            fig_ov = spending_pie_chart(cat_summary)
            if fig_ov is not None:
                st.plotly_chart(fig_ov, use_container_width=True)

    st.divider()

    # ── Row 2: next-month forecast (full width, no nesting) ──────────────────
    if forecast_net is not None:
        section_heading("Next-month forecast", "Ridge regression on your monthly history")
        fa, fb, fc = st.columns(3)
        fa.metric("Expected expense", f"₹{forecast_expense:,.0f}")
        fb.metric("Expected income", f"₹{forecast_income:,.0f}")
        fc.metric(
            "Expected net",
            f"₹{forecast_net:,.0f}",
            delta=f"{'Positive' if forecast_net >= 0 else 'Negative'}",
            delta_color="normal" if forecast_net >= 0 else "inverse",
        )
    elif forecast_note:
        st.warning(forecast_note)

    st.divider()

    # ── Row 3: financial health formulas ────────────────────────────────────
    section_heading(
        "Financial health formulas",
        "Standard ratios calculated from your statement",
    )

    savings_rate = ((income_total - expense_total) / income_total * 100) if income_total > 0 else 0.0
    expense_ratio = (expense_total / income_total * 100) if income_total > 0 else 0.0
    emi_ratio = (share_map.get("EMI", 0) * 100)
    discr_ratio = ((share_map.get("Shopping", 0) + share_map.get("Travel", 0)) * 100)

    h1, h2, h3, h4 = st.columns(4)
    h1.metric(
        "Savings rate",
        f"{savings_rate:.1f}%",
        delta="Target ≥ 20%",
        delta_color="normal" if savings_rate >= 20 else "inverse",
        help="(Income − Expenses) ÷ Income × 100",
    )
    h2.metric(
        "Expense ratio",
        f"{expense_ratio:.1f}%",
        delta="Target ≤ 80%",
        delta_color="normal" if expense_ratio <= 80 else "inverse",
        help="Expenses ÷ Income × 100",
    )
    h3.metric(
        "EMI burden",
        f"{emi_ratio:.1f}%",
        delta="Target ≤ 30%",
        delta_color="normal" if emi_ratio <= 30 else "inverse",
        help="EMI spend ÷ Total expenses × 100",
    )
    h4.metric(
        "Discretionary spend",
        f"{discr_ratio:.1f}%",
        delta="Target ≤ 35%",
        delta_color="normal" if discr_ratio <= 35 else "inverse",
        help="(Shopping + Travel) ÷ Total expenses × 100",
    )

    st.caption(
        "Savings rate = (Income − Expenses) ÷ Income × 100  ·  "
        "Expense ratio = Expenses ÷ Income × 100  ·  "
        "EMI burden = EMI ÷ Total expenses × 100  ·  "
        "Discretionary = (Shopping + Travel) ÷ Total expenses × 100"
    )

elif section == "Spending":
    section_heading(
        "Spending breakdown",
        f"Every expense category · {int(cat_summary['txn_count'].sum()) if not cat_summary.empty else 0:,} rows",
    )
    if cat_summary.empty:
        st.warning("No expense-like transactions found for category analysis.")
    else:
        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            display_cats = cat_summary.copy()
            display_cats["spend_amount"] = display_cats["spend_amount"].map(lambda x: f"₹{x:,.2f}")
            display_cats = display_cats.rename(
                columns={
                    "predicted_category": "Category",
                    "spend_amount": "Total (₹)",
                    "txn_count": "Rows",
                    "share_pct": "Share %",
                }
            )
            st.dataframe(display_cats, use_container_width=True, hide_index=True)
        with c2:
            section_heading("Spending mix")
            fig = spending_pie_chart(cat_summary)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
        top = cat_summary.iloc[0]
        st.caption(
            f"Top: **{top['predicted_category']}** · ₹{top['spend_amount']:,.2f} "
            f"({top['share_pct']}% · {int(top['txn_count'])} rows)"
        )

elif section == "Forecast":
    section_heading("Cash flow forecast", "Walk-forward trained regressors")
    if forecast_note:
        st.warning(forecast_note)
    elif forecast_expense is not None:
        f1, f2, f3 = st.columns(3)
        f1.metric("Next-month expense", f"₹{forecast_expense:,.2f}")
        f2.metric("Next-month income", f"₹{forecast_income:,.2f}")
        f3.metric("Next-month net", f"₹{forecast_net:,.2f}")
        if len(monthly) > 0:
            plot_df = monthly.copy()
            plot_df["YearMonth"] = plot_df["YearMonth"].astype(str)
            fig2 = px.line(
                plot_df,
                x="YearMonth",
                y=["Expense_Amount", "Income_Amount", "Net_Cash_Flow"],
                markers=True,
            )
            plotly_theme(fig2, "Monthly cash flow history")
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Upload statements covering more months to unlock forecasting.")

elif section == "Transactions":
    section_heading("All transactions", f"{len(feat_df):,} rows from your upload")
    txn_display = feat_df[show_cols].copy()
    if "raw_line" in txn_display.columns:
        txn_display["raw_line"] = txn_display["raw_line"].map(redact_narration)
    st.caption("Narrations are masked in the table (full text stays in memory for parsing/classification only).")
    st.dataframe(txn_display, use_container_width=True, height=520)

elif section == "Advisor":
    section_heading(
        "FinGuide Advisor",
        "Optional cloud chat sends anonymized totals only — not your PDF or raw statement lines.",
    )
    st.caption(
        "Groq receives category totals, risk score, and your chat messages — not PDFs or full narrations."
    )
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

    if ChatGroq is None:
        st.warning("Install LangChain Groq (`pip install langchain-groq`) and restart.")
    elif not groq_key:
        st.info(
            "Add `GROQ_API_KEY` in Streamlit **Secrets** (Cloud) or `.env` (local) to enable chat."
        )
    else:
        if "advisor_messages" not in st.session_state:
            st.session_state.advisor_messages = []

        context_blob = build_advisor_context(
            feat_df=feat_df,
            cat_summary=cat_summary,
            income_total=income_total,
            expense_total=expense_total,
            forecast_expense=forecast_expense,
            forecast_income=forecast_income,
            forecast_net=forecast_net,
            risk_level=level,
            risk_score=score,
            risk_reasons=reasons,
        )

        advisor_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ADVISOR_SYSTEM_PROMPT),
                ("system", "ANONYMIZED_STATEMENT_SUMMARY:\n{context_blob}"),
                MessagesPlaceholder("history"),
                ("human", "{user_query}"),
            ]
        )

        head_l, head_r = st.columns([4, 1])
        with head_r:
            if st.button("Clear chat", use_container_width=True):
                st.session_state.advisor_messages = []
                st.rerun()

        chat_box = st.container(height=400)
        with chat_box:
            if not st.session_state.advisor_messages:
                with st.chat_message("assistant"):
                    top_cat = (
                        cat_summary.iloc[0]["predicted_category"]
                        if not cat_summary.empty
                        else "your categories"
                    )
                    st.markdown(
                        f"Hey — I've looked through **{len(feat_df):,}** transactions from your upload.\n\n"
                        f"You're at **₹{net_total:,.0f}** net cash flow this period, "
                        f"risk is **{level}**, and your biggest spend bucket is **{top_cat}**.\n\n"
                        "Ask me anything — where you're overspending, how to save more, "
                        "or what that risk score actually means."
                    )
            for msg in st.session_state.advisor_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        st.caption("Quick prompts — tap to fill the box, then send")
        p1, p2, p3 = st.columns(3)
        suggestions = [
            p1.button("Where am I overspending?", use_container_width=True),
            p2.button("How can I save more?", use_container_width=True),
            p3.button("Explain my risk score", use_container_width=True),
        ]
        preset = None
        if suggestions[0]:
            preset = "Where am I overspending?"
        elif suggestions[1]:
            preset = "How can I save more this month?"
        elif suggestions[2]:
            preset = "Explain my risk score in simple terms."

        user_q = st.chat_input("Ask FinGuide anything about your money…", key="advisor_chat_input")
        send_q = preset or user_q

        if send_q:
            st.session_state.advisor_messages.append({"role": "user", "content": send_q})
            llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0.45)
            history_msgs = []
            for m in st.session_state.advisor_messages[:-1][-10:]:
                if m["role"] == "user":
                    history_msgs.append(HumanMessage(content=m["content"]))
                else:
                    history_msgs.append(AIMessage(content=m["content"]))
            lc_messages = advisor_prompt.format_messages(
                context_blob=context_blob,
                history=history_msgs,
                user_query=send_q,
            )
            try:
                with st.spinner("FinGuide is typing…"):
                    resp = llm.invoke(lc_messages)
                answer = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                answer = (
                    "Sorry — I couldn't reach the model just now. "
                    f"Try again in a moment. ({e})"
                )
            st.session_state.advisor_messages.append({"role": "assistant", "content": answer})
            st.rerun()
