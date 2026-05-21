"""
Indian bank statement PDF parser.

Layout types seen across major banks (HDFC, SBI, ICICI, Axis, Kotak, etc.):
  A) One PDF table row per transaction (SBI, many ICICI exports).
  B) Stacked cells — all dates/amounts in one row, newline-separated (HDFC netbanking PDF).
  C) Plain text lines with date at start (fallback / scanned PDFs).

Pipeline per document:
  1. Detect bank from first-page text.
  2. Per page, score candidate extractors and keep the best result.
  3. Validate rows (sane amounts, real dates) and deduplicate.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

import numpy as np
import pandas as pd
import pdfplumber

# ---------------------------------------------------------------------------
# Column keywords — longer / specific phrases first within each list
# ---------------------------------------------------------------------------
_COL_KEYWORDS: dict[str, list[str]] = {
    "date": [
        "transaction date", "txn date", "tran date", "trans date",
        "value date", "posting date", "value dt", "date",
    ],
    "description": [
        "transaction remarks", "transaction details", "particulars",
        "narration", "description", "remarks", "details",
    ],
    "ref": [
        "chq./ref.no.", "chq/ref. no.", "chq/ref", "ref no.",
        "cheque no", "reference", "instrument", "chq", "ref",
    ],
    "debit": [
        "withdrawal amt", "withdrawal amount", "withdrawal",
        "debit amount", "amount(dr)", "debit", "withdrawl",
    ],
    "credit": [
        "deposit amt", "deposit amount", "deposit",
        "credit amount", "amount(cr)", "credit",
    ],
    "balance": ["closing balance", "running balance", "balance", "avl bal"],
}

BANK_CONFIGS: dict[str, dict[str, list[str]]] = {
    "hdfc": {
        "date": ["value dt", "date"],
        "description": ["narration"],
        "debit": ["withdrawal amt", "withdrawal"],
        "credit": ["deposit amt", "deposit"],
        "balance": ["closing balance"],
    },
    "sbi": {
        "description": ["particulars", "narration"],
        "debit": ["debit", "withdrawal"],
        "credit": ["credit", "deposit"],
    },
    "icici": {
        "description": ["transaction remarks", "narration"],
        "ref": ["ref no./cheque no", "ref no"],
    },
    "axis": {
        "debit": ["withdrawal amount", "debit"],
        "credit": ["deposit amount", "credit"],
    },
    "kotak": {
        "debit": ["withdrawals", "debit"],
        "credit": ["deposits", "credit"],
    },
    "generic": {},
}

_BANK_SIGNATURES: list[tuple[str, list[str]]] = [
    ("sbi", ["state bank of india", "sbi.co.in", "sbi bank"]),
    ("hdfc", ["hdfc bank", "hdfcbank.com", "hdfcbanklimited", "rtgs/neftifsc: hdfc"]),
    ("icici", ["icici bank", "icicibank.com"]),
    ("axis", ["axis bank", "axisbank.com"]),
    ("kotak", ["kotak mahindra", "kotakbank.com"]),
    ("yes", ["yes bank", "yesbank.in"]),
    ("pnb", ["punjab national bank", "pnbindia.in"]),
    ("bob", ["bank of baroda", "bankofbaroda"]),
    ("canara", ["canara bank", "canarabank.in"]),
    ("indusind", ["indusind bank", "indusind.com"]),
    ("idfc", ["idfc first bank", "idfcfirstbank"]),
    ("federal", ["federal bank", "federalbank.co.in"]),
    ("rbl", ["rbl bank", "rblbank.com"]),
]

# Banks that commonly ship stacked-cell PDFs
_STACKED_TEXT_BANKS = frozenset({"hdfc", "kotak"})

_MONEY_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*\.\d{2})\b")
_TXN_START_RE = re.compile(r"^(\d{2}[/\-.]\d{2}[/\-.]\d{2,4})\s")
_DATE_FORMATS = [
    "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%d-%b-%Y", "%d-%b-%y",
]

_SKIP_ROW_PATTERNS = re.compile(
    r"opening\s*balance|closing\s*balance|statement\s*summary|"
    r"generated\s*on|drcount|crcount|total\s*debit|total\s*credit",
    re.IGNORECASE,
)
_FOOTER_PATTERNS = re.compile(
    r"statementsummary|openingbalance|generatedon|hdfcbanklimited|"
    r"contentsofthis|registered\s*office|gstin",
    re.IGNORECASE,
)

EXPECTED_COLS = ["raw_line", "date", "amount", "txn_type"]
_MAX_SANE_AMOUNT = 50_000_000.0  # ₹5 crore — flag obvious parse errors


def detect_bank(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower())
    for slug, sigs in _BANK_SIGNATURES:
        if any(sig in t for sig in sigs):
            return slug
    return "generic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(val) -> pd.Timestamp:
    if val is None:
        return pd.NaT
    s = re.sub(r"\s+", " ", str(val)).strip()
    s = re.sub(r"^\d+[\.\s]+", "", s).strip()
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(datetime.strptime(s, fmt).date())
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, dayfirst=True)
    except Exception:
        return pd.NaT


def _parse_amount(val) -> float:
    if val is None:
        return np.nan
    s = str(val).strip()
    if not s or s in ("-", "–", "—", "N/A", "na", ""):
        return np.nan
    s = re.sub(r"\s*(Dr|Cr|DR|CR)\b\.?", "", s)
    s = re.sub(r"[₹Rs,\s]", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s:
        return np.nan
    try:
        return abs(float(s))
    except ValueError:
        return np.nan


def _header_tokens(cell: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", cell.lower())


def _kw_matches_header(kw: str, header_cell: str) -> bool:
    """Match keyword to header without false positives (e.g. credit in description)."""
    cell = header_cell.lower().strip()
    kw = kw.lower().strip()
    if not cell or not kw:
        return False
    # Short tokens: whole-word only (dr, cr)
    if len(kw) <= 3:
        return kw in _header_tokens(cell)
    # Multi-word phrase: substring of header cell is OK
    if " " in kw or "/" in kw or "." in kw:
        return kw in cell
    # Single long word: must be its own token, not buried inside another word
    return kw in _header_tokens(cell)


def _resolve_columns(header: list[str], bank: str) -> dict[str, int] | None:
    cfg: dict[str, list[str]] = {}
    for field, defaults in _COL_KEYWORDS.items():
        overrides = BANK_CONFIGS.get(bank, {}).get(field, [])
        # bank-specific phrases first, then defaults (longest first)
        seen: set[str] = set()
        merged: list[str] = []
        for kw in overrides + defaults:
            if kw not in seen:
                seen.add(kw)
                merged.append(kw)
        cfg[field] = sorted(merged, key=len, reverse=True)

    used: set[int] = set()
    col_map: dict[str, int] = {}

    # Assign balance last; amount columns before description-like fields
    field_order = ["date", "debit", "credit", "ref", "description", "balance"]
    for field in field_order:
        keywords = cfg.get(field, [])
        for idx, cell in enumerate(header):
            if idx in used:
                continue
            if any(_kw_matches_header(kw, cell) for kw in keywords):
                col_map[field] = idx
                used.add(idx)
                break

    if "date" not in col_map or "description" not in col_map:
        return None
    if "debit" not in col_map and "credit" not in col_map:
        return None
    return col_map


def _infer_txn_type(desc: str, debit: float, credit: float, balance_dir: str | None) -> str:
    if balance_dir:
        return balance_dir
    if not pd.isna(debit) and pd.isna(credit):
        return "Expense"
    if not pd.isna(credit) and pd.isna(debit):
        return "Income"
    upper = desc.upper()
    credit_markers = (
        "CR-", "NEFTCR", "IMPS-CR", "IBFUNDSTRANSFERCR", "SALARY",
        "REFUND", "INTEREST CREDIT", "CASHBACK", "DEPOSIT", "/CR/",
    )
    if any(m in upper for m in credit_markers):
        return "Income"
    debit_markers = ("DR-", "RTGSDR", "IBFUNDSTRANSFERDR", "WITHDRAWAL", "/DR/")
    if any(m in upper for m in debit_markers):
        return "Expense"
    return "Expense"


def _row_dict(desc: str, ref: str, amount: float, date_val, txn_type: str) -> dict:
    desc = re.sub(r"\s+", " ", desc).strip()
    ref = ref.strip()
    parts = [desc]
    if ref and ref not in ("-", "–"):
        parts.append(f"Ref:{ref}")
    parts.append(f"Amount: INR {amount:.2f}")
    return {
        "raw_line": " | ".join(parts),
        "date": date_val,
        "amount": amount,
        "txn_type": txn_type,
    }


def _is_valid_row(row: dict) -> bool:
    if pd.isna(row.get("date")) or pd.isna(row.get("amount")):
        return False
    amt = float(row["amount"])
    if amt <= 0 or amt > _MAX_SANE_AMOUNT:
        return False
    if _SKIP_ROW_PATTERNS.search(row.get("raw_line", "")):
        return False
    return True


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        key = (
            str(r.get("date", ""))[:10],
            round(float(r["amount"]), 2),
            r.get("raw_line", "")[:80],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Extractor A — structured table (one row per transaction)
# ---------------------------------------------------------------------------

def _find_header_row(table: list[list], bank: str) -> tuple[int, dict[str, int]] | None:
    for i, row in enumerate(table[:8]):
        if not row:
            continue
        header = [
            re.sub(r"\s+", " ", str(c).replace("\n", " ")).strip().lower()
            if c is not None else ""
            for c in row
        ]
        col_map = _resolve_columns(header, bank)
        if col_map is not None:
            return i, col_map
    return None


def _extract_table_rows(table: list[list], bank: str) -> list[dict]:
    result = _find_header_row(table, bank)
    if result is None:
        return []
    header_idx, col_map = result
    rows: list[dict] = []

    for raw_row in table[header_idx + 1 :]:
        if not raw_row:
            continue

        def cell(field: str):
            idx = col_map.get(field)
            if idx is None or idx >= len(raw_row):
                return None
            return raw_row[idx]

        date_val = _parse_date(cell("date"))
        if pd.isna(date_val):
            continue

        desc = str(cell("description") or "").replace("\n", " ").strip()
        if not desc or desc in ("-", "–"):
            continue
        if _SKIP_ROW_PATTERNS.search(desc):
            continue

        ref = str(cell("ref") or "").replace("\n", " ").strip()
        debit = _parse_amount(cell("debit"))
        credit = _parse_amount(cell("credit"))

        if pd.isna(debit) and pd.isna(credit):
            continue

        amount = debit if not pd.isna(debit) else credit
        txn_type = _infer_txn_type(desc, debit, credit, None)
        row = _row_dict(desc, ref, amount, date_val, txn_type)
        if _is_valid_row(row):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Extractor B — stacked table cells (unzip newline-separated columns)
# ---------------------------------------------------------------------------

def _is_stacked_table(table: list[list]) -> bool:
    for row in table[:4]:
        if not row:
            continue
        counts = [str(c).count("\n") for c in row if c]
        if sum(1 for n in counts if n >= 4) >= 3:
            return True
    return False


def _unstack_table(table: list[list], bank: str) -> list[dict]:
    """Split HDFC-style stacked cells when date column has N newline-separated dates."""
    result = _find_header_row(table, bank)
    if result is None:
        return []
    header_idx, col_map = result

    # Collect data rows (skip header); merge continuation rows without dates
    data_rows = [r for r in table[header_idx + 1 :] if r and any(str(c or "").strip() for c in r)]
    if not data_rows:
        return []

    # If single mega-row with newlines, unzip columns
    mega = data_rows[0]
    date_idx = col_map.get("date", 0)
    date_lines = str(mega[date_idx] if date_idx < len(mega) else "").split("\n")
    date_lines = [d.strip() for d in date_lines if d.strip()]
    if len(date_lines) < 2:
        return []

    def col_lines(field: str) -> list[str]:
        idx = col_map.get(field)
        if idx is None or idx >= len(mega):
            return [""] * len(date_lines)
        parts = str(mega[idx] or "").split("\n")
        # pad / trim to date count
        if len(parts) < len(date_lines):
            parts.extend([""] * (len(date_lines) - len(parts)))
        return parts[: len(date_lines)]

    d_lines = col_lines("description")
    r_lines = col_lines("ref")
    w_lines = col_lines("debit")
    c_lines = col_lines("credit")

    rows: list[dict] = []
    for i, d_str in enumerate(date_lines):
        date_val = _parse_date(d_str)
        if pd.isna(date_val):
            continue
        desc = d_lines[i].replace("\n", " ").strip() if i < len(d_lines) else ""
        if not desc:
            continue
        ref = r_lines[i].strip() if i < len(r_lines) else ""
        debit = _parse_amount(w_lines[i] if i < len(w_lines) else None)
        credit = _parse_amount(c_lines[i] if i < len(c_lines) else None)
        if pd.isna(debit) and pd.isna(credit):
            continue
        amount = debit if not pd.isna(debit) else credit
        txn_type = _infer_txn_type(desc, debit, credit, None)
        row = _row_dict(desc, ref, amount, date_val, txn_type)
        if _is_valid_row(row):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Extractor C — text blocks (HDFC multi-line narration)
# ---------------------------------------------------------------------------

def _extract_text_blocks(page_text: str, prev_balance: float | None) -> tuple[list[dict], float | None]:
    lines = page_text.splitlines()
    start_idx = len(lines)

    for i, line in enumerate(lines):
        if re.search(
            r"(Narration|WithdrawalAmt|DepositAmt|Withdrawal\s*\(|Description\s+Chq)",
            line,
            re.IGNORECASE,
        ):
            start_idx = i + 1
            break

    if start_idx == len(lines):
        for i, line in enumerate(lines):
            if _TXN_START_RE.match(line.strip()):
                start_idx = i
                break

    blocks: list[str] = []
    current: str | None = None

    for line in lines[start_idx:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _FOOTER_PATTERNS.search(stripped.replace(" ", "")):
            break
        if _TXN_START_RE.match(stripped):
            if current:
                blocks.append(current)
            current = stripped
        elif current:
            current += " " + stripped

    if current:
        blocks.append(current)

    rows: list[dict] = []
    for block in blocks:
        if _SKIP_ROW_PATTERNS.search(block):
            continue
        date_m = _TXN_START_RE.match(block)
        if not date_m:
            continue
        date_val = _parse_date(date_m.group(1))
        if pd.isna(date_val):
            continue

        amounts = _MONEY_RE.findall(block)
        if len(amounts) < 2:
            continue

        balance = _parse_amount(amounts[-1])
        txn_amount = _parse_amount(amounts[-2])
        if pd.isna(balance) or pd.isna(txn_amount):
            continue

        if prev_balance is not None:
            txn_type = "Income" if balance > prev_balance else "Expense"
        else:
            txn_type = _infer_txn_type(block, np.nan, np.nan, None)

        prev_balance = balance

        desc = block
        for amt_str in reversed(amounts[-2:]):
            pos = desc.rfind(amt_str)
            if pos != -1:
                desc = desc[:pos]
        # Drop leading date and inline value-date tokens
        desc = _TXN_START_RE.sub("", desc, count=1)
        desc = re.sub(r"\b\d{2}[/\-.]\d{2}[/\-.]\d{2,4}\b", " ", desc)
        desc = re.sub(r"\b\d{10,}\b", " ", desc)  # long ref numbers
        desc = re.sub(r"\s+", " ", desc).strip()

        row = _row_dict(desc, "", txn_amount, date_val, txn_type)
        if _is_valid_row(row):
            rows.append(row)

    return rows, prev_balance


# ---------------------------------------------------------------------------
# Page-level strategy
# ---------------------------------------------------------------------------

def _parse_page(
    page,
    bank: str,
    prev_balance: float | None,
) -> tuple[list[dict], float | None, str]:
    """Return (rows, updated_balance, strategy_used)."""
    page_text = page.extract_text() or ""
    tables = page.extract_tables() or []
    candidates: list[tuple[str, list[dict]]] = []

    for table in tables:
        if not table or len(table) < 2:
            continue
        if _is_stacked_table(table):
            unstacked = _unstack_table(table, bank)
            if unstacked:
                candidates.append(("unstack", unstacked))
        else:
            structured = _extract_table_rows(table, bank)
            if structured:
                candidates.append(("table", structured))
            if bank != "generic":
                structured_g = _extract_table_rows(table, "generic")
                if len(structured_g) > len(structured):
                    candidates.append(("table_generic", structured_g))

    # Text-block parser for HDFC-style pages (often better than unstack for narration)
    text_balance = prev_balance
    if bank in _STACKED_TEXT_BANKS or any(_is_stacked_table(t) for t in tables):
        text_rows, text_balance = _extract_text_blocks(page_text, prev_balance)
        if text_rows:
            candidates.append(("text", text_rows))

    if not candidates:
        return [], prev_balance, "none"

    # Pick extractor with most valid rows; tie-break: text > table > unstack
    priority = {"text": 3, "table": 2, "table_generic": 2, "unstack": 1}
    best_name, best_rows = max(
        candidates,
        key=lambda x: (len(x[1]), priority.get(x[0], 0)),
    )
    if best_name == "text":
        prev_balance = text_balance
    return best_rows, prev_balance, best_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf_transactions(pdf_bytes: bytes) -> pd.DataFrame:
    rows: list[dict] = []
    prev_balance: float | None = None
    bank = "generic"

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return pd.DataFrame(columns=EXPECTED_COLS)

        bank = detect_bank(pdf.pages[0].extract_text() or "")

        for page in pdf.pages:
            page_rows, prev_balance, _ = _parse_page(page, bank, prev_balance)
            rows.extend(page_rows)

    if not rows:
        return pd.DataFrame(columns=EXPECTED_COLS)

    rows = _dedupe_rows(rows)
    out = pd.DataFrame(rows)
    for col in EXPECTED_COLS:
        if col not in out.columns:
            out[col] = np.nan
    return out[EXPECTED_COLS].reset_index(drop=True)
