"""Privacy helpers: redaction and minimal LLM context (no change to ML/parser logic)."""

from __future__ import annotations

import re

import pandas as pd

# Mask account / card / long numeric runs in narrations shown in UI
_DIGIT_RUN = re.compile(r"\d{6,}")
_REF_TAG = re.compile(r"\|\s*Ref:[a-z0-9]+", re.IGNORECASE)
_AMT_TAIL = re.compile(r"\|\s*Amount:.*$", re.IGNORECASE)
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def redact_narration(text: str) -> str:
    """Mask likely PII in transaction text for display and outbound API payloads."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text)
    s = _REF_TAG.sub("| Ref:***", s)
    s = _AMT_TAIL.sub("| Amount: ***", s)
    s = _EMAIL.sub("***@***", s)
    s = _DIGIT_RUN.sub(lambda m: "*" * min(len(m.group()), 12), s)
    return s


def uploads_fingerprint(uploaded_files) -> tuple:
    """Stable id for current upload set — used to reset chat when files change."""
    return tuple((uf.name, uf.size) for uf in uploaded_files)


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
    """
    Aggregates-only briefing for the LLM.
    No raw narrations, file names, or row-level merchant text.
    """
    transfer_rows = int((feat_df["predicted_category"] == "Transfer").sum()) if "predicted_category" in feat_df else 0
    unclassified_rows = int((feat_df["predicted_category"] == "Unclassified").sum()) if "predicted_category" in feat_df else 0

    lines = [
        "[Anonymized summary — no account numbers or transaction narrations below.]",
        "",
        "## Statement snapshot",
        f"- Transaction count: {len(feat_df):,}",
        f"- Income total (INR): {round(float(income_total), 0):,.0f}",
        f"- Expense total excl. transfers (INR): {round(float(expense_total), 0):,.0f}",
        f"- Net cash flow (INR): {round(float(income_total - expense_total), 0):,.0f}",
        f"- Rows tagged Transfer: {transfer_rows:,}",
        f"- Rows tagged Unclassified: {unclassified_rows:,}",
        "",
        "## Risk profile",
        f"- Level: {risk_level} (score {risk_score}/100)",
    ]
    if risk_reasons:
        for r in risk_reasons:
            lines.append(f"- {r}")
    else:
        lines.append("- No major flags in this period.")

    lines.append("")
    lines.append("## Spending by category (INR, row counts)")
    if cat_summary.empty:
        lines.append("- No expense categories available.")
    else:
        for _, row in cat_summary.iterrows():
            lines.append(
                f"- {row['predicted_category']}: {round(float(row['spend_amount']), 0):,.0f} "
                f"({row['share_pct']}% of spend, {int(row['txn_count'])} rows)"
            )

    lines.append("")
    lines.append("## Next-month forecast (INR)")
    if forecast_expense is None:
        lines.append("- Not available for this upload.")
    else:
        lines.append(f"- Expected expense: {round(float(forecast_expense), 0):,.0f}")
        lines.append(f"- Expected income: {round(float(forecast_income), 0):,.0f}")
        lines.append(f"- Expected net: {round(float(forecast_net), 0):,.0f}")

    return "\n".join(lines)


PRIVACY_SIDEBAR_NOTE = """\
**Data handling**

FinGuide runs on **Streamlit** over HTTPS. Your upload is processed in **server memory** for this session only — not saved to disk and not stored in a database.

**In the app**
- Parsing, ML, charts, and PDF export use session data only
- Transaction narrations are **masked** in the table view
- Session ends when you close the tab; chat resets on new uploads
"""
