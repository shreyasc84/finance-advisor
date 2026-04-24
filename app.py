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

try:
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
except Exception:  # pragma: no cover
    ChatGroq = None
    HumanMessage = SystemMessage = AIMessage = None
    ChatPromptTemplate = MessagesPlaceholder = None


st.set_page_config(page_title="AI Personal Finance Advisor", layout="wide")
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
    rows = []
    table_rows_found = 0
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            # First pass: structured table parsing (best for bank statements)
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = [str(c).strip().lower() if c is not None else "" for c in (table[1] or [])]
                if not any("date" in h for h in header) or not any("description" in h for h in header):
                    continue
                # Expected columns: #, Date, Description, Chq/Ref. No., Withdrawal, Deposit, Balance
                for r in table[2:]:
                    if not r or len(r) < 7:
                        continue
                    date_val = parse_statement_date(r[1])
                    if pd.isna(date_val):
                        continue
                    desc = str(r[2] or "").replace("\n", " ").strip()
                    ref = str(r[3] or "").replace("\n", " ").strip()
                    wd = parse_amount_cell(r[4])
                    dep = parse_amount_cell(r[5])
                    if pd.isna(wd) and pd.isna(dep):
                        continue
                    amount = wd if not pd.isna(wd) else dep
                    txn_type = "Expense" if not pd.isna(wd) else "Income"
                    raw_line = f"{desc} | Ref:{ref} | Amount: INR {amount:.2f}"
                    rows.append(
                        {
                            "raw_line": raw_line,
                            "date": date_val,
                            "amount": amount,
                            "txn_type": txn_type,
                        }
                    )
                    table_rows_found += 1

            # Fallback: free-text parsing (kept for non-tabular PDFs)
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if len(line) < 8:
                    continue
                amt = extract_amount(line)
                if pd.isna(amt):
                    continue
                rows.append(
                    {
                        "raw_line": line,
                        "date": parse_date_from_text(line),
                        "amount": amt,
                        "txn_type": infer_txn_type(line),
                    }
                )
    # If table extraction worked, keep those rows only (avoids disclaimer noise from fallback parser)
    if table_rows_found > 0:
        rows = [r for r in rows if " | Ref:" in r["raw_line"] and " | Amount: INR " in r["raw_line"]]
    out = pd.DataFrame(rows)
    expected_cols = ["raw_line", "date", "amount", "txn_type"]
    if out.empty:
        return pd.DataFrame(columns=expected_cols)
    for col in expected_cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[expected_cols]


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
    s = f"{raw_line} {merchant_text}".lower()
    transfer_tokens = [
        "upi/mr ",
        "upi/mrs ",
        "upi/ms ",
        "upi/miss ",
        "pay to",
        "merchant qr",
        "self",
        "to self",
        "redeem",
        "erupee",
    ]
    return any(tok in s for tok in transfer_tokens)


def risk_profile(expense_total, income_total, category_share, forecast_net):
    score = 0
    reasons = []
    savings_rate = (income_total - expense_total) / income_total if income_total > 0 else -1

    if income_total <= 0:
        score += 35
        reasons.append("No reliable income detected in uploaded statement.")
    elif savings_rate < 0:
        score += 30
        reasons.append("Expenses exceed income in observed period.")
    elif savings_rate < 0.15:
        score += 15
        reasons.append("Low savings rate (<15%).")

    emi_share = category_share.get("EMI", 0)
    if emi_share > 0.30:
        score += 25
        reasons.append("High EMI concentration (>30% of spending).")
    elif emi_share > 0.20:
        score += 12
        reasons.append("Moderate EMI concentration (>20%).")

    discretionary = category_share.get("Shopping", 0) + category_share.get("Travel", 0)
    if discretionary > 0.50:
        score += 20
        reasons.append("High discretionary spend (Shopping + Travel >50%).")
    elif discretionary > 0.35:
        score += 10
        reasons.append("Moderate discretionary spend (>35%).")

    if forecast_net is not None and forecast_net < 0:
        score += 20
        reasons.append("Forecasted next-month net cash flow is negative.")

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


def build_advisor_context(
    feat_df: pd.DataFrame,
    cat_summary: pd.DataFrame,
    income_total: float,
    expense_total: float,
    forecast_expense,
    forecast_income,
    forecast_net,
    risk_level: str,
    risk_score: int,
    risk_reasons: list,
) -> str:
    top_cats = cat_summary.head(8).to_dict(orient="records") if not cat_summary.empty else []
    sample_txns = (
        feat_df[["date", "txn_type", "amount", "predicted_category", "raw_line"]]
        .head(15)
        .to_dict(orient="records")
    )
    context = {
        "summary": {
            "transaction_rows": int(len(feat_df)),
            "income_total": round(float(income_total), 2),
            "expense_total": round(float(expense_total), 2),
            "net_observed": round(float(income_total - expense_total), 2),
        },
        "category_spending_top": top_cats,
        "forecast": {
            "next_month_expense": None if forecast_expense is None else round(float(forecast_expense), 2),
            "next_month_income": None if forecast_income is None else round(float(forecast_income), 2),
            "next_month_net_cash_flow": None if forecast_net is None else round(float(forecast_net), 2),
        },
        "risk_profile": {
            "level": risk_level,
            "score_100": int(risk_score),
            "reasons": risk_reasons,
        },
        "sample_transactions": sample_txns,
    }
    return str(context)


st.title("AI-Powered Personal Finance Advisor")
st.caption("Upload bank statement PDF/CSV -> classify transactions, forecast cash flow, and estimate risk profile.")

uploaded_files = st.file_uploader(
    "Upload statement files (PDF or CSV). You can upload multiple files.",
    type=["pdf", "csv"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Upload at least one statement to run analysis.")
    st.stop()

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

st.subheader("Parsed Transactions")
st.write(f"Detected transaction rows: **{len(txn_df):,}**")

# Classification block
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

# Unified transaction table (parsed + predicted) moved under Parsed Transactions
show_cols = ["source_file", "date", "txn_type", "amount", "predicted_category", "raw_line"]
if "pred_confidence" in feat_df.columns:
    show_cols.insert(5, "pred_confidence")
st.dataframe(feat_df[show_cols], use_container_width=True, height=420)

# Focus classification on expenses
expense_df = feat_df[feat_df["txn_type"] == "Expense"].copy()
if expense_df.empty:
    expense_df = feat_df.copy()

cat_summary = (
    expense_df.groupby("predicted_category")["amount"]
    .sum()
    .sort_values(ascending=False)
    .rename("spend_amount")
    .reset_index()
)
total_expense = cat_summary["spend_amount"].sum() if not cat_summary.empty else 0.0
cat_summary["share_pct"] = (cat_summary["spend_amount"] / total_expense * 100).round(2) if total_expense > 0 else 0

st.subheader("Category Spending Analysis")
if cat_summary.empty:
    st.warning("No expense-like transactions found for category analysis.")
else:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(cat_summary, use_container_width=True)
    with c2:
        fig = px.pie(cat_summary, names="predicted_category", values="spend_amount", title="Spending Mix by Category")
        st.plotly_chart(fig, use_container_width=True)
    top_cat = cat_summary.iloc[0]["predicted_category"]
    top_amt = cat_summary.iloc[0]["spend_amount"]
    st.success(f"Highest spend category: **{top_cat}** (INR {top_amt:,.2f})")

# Regression block
forecast_expense = None
forecast_income = None
forecast_net = None

income_total = feat_df.loc[feat_df["txn_type"] == "Income", "amount"].sum()
expense_total = feat_df.loc[feat_df["txn_type"] == "Expense", "amount"].sum()

st.subheader("Cash Flow Forecast")
if not os.path.exists(REGRESSOR_PATH):
    st.warning(f"Missing regressor model: `{REGRESSOR_PATH}`. Forecast skipped.")
else:
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
        st.warning("Not enough monthly history to forecast. Upload statements spanning more months.")
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

        c1, c2, c3 = st.columns(3)
        c1.metric("Forecast Next-Month Expense", f"INR {forecast_expense:,.2f}")
        c2.metric("Forecast Next-Month Income", f"INR {forecast_income:,.2f}")
        c3.metric("Forecast Next-Month Net Cash Flow", f"INR {forecast_net:,.2f}")

        if len(monthly) > 0:
            plot_df = monthly.copy()
            plot_df["YearMonth"] = plot_df["YearMonth"].astype(str)
            fig2 = px.line(
                plot_df,
                x="YearMonth",
                y=["Expense_Amount", "Income_Amount", "Net_Cash_Flow"],
                markers=True,
                title="Historical Monthly Cash Flow",
            )
            st.plotly_chart(fig2, use_container_width=True)

# Risk profile
st.subheader("Risk Profile")
share_map = {}
if total_expense > 0 and not cat_summary.empty:
    share_map = dict(zip(cat_summary["predicted_category"], cat_summary["share_pct"] / 100.0))

level, score, reasons = risk_profile(expense_total, income_total, share_map, forecast_net)
color = {"Low Risk": "green", "Medium Risk": "orange", "High Risk": "red"}[level]
st.markdown(f"**Risk Level:** :{color}[{level}]  \n**Risk Score:** {score}/100")
for r in reasons:
    st.write(f"- {r}")

# LLM advisor chat block
st.subheader("Financial Advisor Chat")
groq_key = os.getenv("GROQ_API_KEY", "").strip()
groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

if ChatGroq is None:
    st.warning("LangChain Groq package missing. Install requirements and restart app.")
elif not groq_key:
    st.info("Add `GROQ_API_KEY` to `.env` file to enable advisor chat.")
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
            (
                "system",
                (
                    "You are FinGuide, an Indian personal finance advisor.\n"
                    "You MUST use the model output context as primary evidence.\n"
                    "Never claim guaranteed returns, never ask user to take illegal tax shortcuts, "
                    "and never provide medical/legal advice.\n\n"
                    "Response quality rubric (always satisfy):\n"
                    "1) Give a plain-language diagnosis in 2-4 bullets.\n"
                    "2) Give a prioritized action plan with exact numbers where possible.\n"
                    "3) Mention one key risk and one fallback option.\n"
                    "4) If data is incomplete, state what is missing.\n"
                    "5) End with a 30-day practical checklist.\n\n"
                    "Tone: practical, supportive, direct. Avoid fluff."
                ),
            ),
            ("system", "MODEL_OUTPUT_CONTEXT:\n{context_blob}"),
            MessagesPlaceholder("history"),
            ("human", "{user_query}"),
        ]
    )

    # Render chat history
    for msg in st.session_state.advisor_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_q = st.chat_input("Ask for advice (budgeting, spending cuts, risk reduction, savings plan)...")
    if user_q:
        st.session_state.advisor_messages.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        llm = ChatGroq(api_key=groq_key, model=groq_model, temperature=0.15)
        history_msgs = []
        for m in st.session_state.advisor_messages[-8:]:
            if m["role"] == "user":
                history_msgs.append(HumanMessage(content=m["content"]))
            else:
                history_msgs.append(AIMessage(content=m["content"]))

        lc_messages = advisor_prompt.format_messages(
            context_blob=context_blob,
            history=history_msgs,
            user_query=user_q,
        )

        try:
            resp = llm.invoke(lc_messages)
            answer = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            answer = f"Could not get LLM response right now: {e}"

        st.session_state.advisor_messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)
