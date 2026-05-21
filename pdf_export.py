"""Professional PDF summary export for FinGuide (fpdf2 + matplotlib)."""

from __future__ import annotations

import os
from datetime import datetime
from io import BytesIO

_mpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mplconfig")
os.makedirs(_mpl_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _mpl_dir)

import matplotlib.pyplot as plt
from fpdf import FPDF

# Brand palette (RGB)
NAVY = (17, 24, 39)
ACCENT = (37, 99, 235)
ACCENT_LIGHT = (239, 246, 255)
SLATE = (107, 114, 128)
BORDER = (229, 231, 235)
ROW_ALT = (249, 250, 251)
WHITE = (255, 255, 255)

CHART_COLORS = ["#2563eb", "#f97316", "#16a34a", "#9333ea", "#0891b2", "#e11d48"]

MARGIN_L = 20
MARGIN_R = 20
MARGIN_T = 32
MARGIN_B = 22
PAGE_W = 210


class FinGuidePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=MARGIN_B)
        self.set_margins(MARGIN_L, MARGIN_T, MARGIN_R)
        self.content_w = PAGE_W - MARGIN_L - MARGIN_R
        self._report_date = datetime.now().strftime("%d %b %Y, %H:%M")
        self._source_names = ""

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 26, style="F")
        self.set_xy(MARGIN_L, 8)
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(*WHITE)
        self.cell(0, 8, "FinGuide", ln=True)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(200, 210, 220)
        self.set_x(MARGIN_L)
        self.cell(0, 5, "Personal finance statement report", ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(14)

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*BORDER)
        self.line(MARGIN_L, self.get_y(), PAGE_W - MARGIN_R, self.get_y())
        self.ln(3)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*SLATE)
        self.cell(
            0,
            4,
            f"Page {self.page_no()}  |  Generated {self._report_date}  |  Not financial advice",
            align="C",
        )

    def meta_block(self, file_names: list[str]):
        self._source_names = ", ".join(file_names[:4])
        if len(file_names) > 4:
            self._source_names += f" (+{len(file_names) - 4} more)"
        self.set_fill_color(*ACCENT_LIGHT)
        self.set_draw_color(*ACCENT)
        self.rect(MARGIN_L, self.get_y(), self.content_w, 18, style="DF")
        y0 = self.get_y() + 4
        self.set_xy(MARGIN_L + 6, y0)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*SLATE)
        self.cell(0, 5, f"Generated: {self._report_date}", ln=True)
        self.set_x(MARGIN_L + 6)
        self.multi_cell(self.content_w - 12, 5, f"Source: {self._source_names}")
        self.set_text_color(0, 0, 0)
        self.ln(10)

    def section_title(self, title: str):
        self.ln(5)
        self.set_fill_color(*ACCENT_LIGHT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        y = self.get_y()
        self.rect(MARGIN_L, y, self.content_w, 9, style="DF")
        self.set_xy(MARGIN_L + 5, y + 2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*NAVY)
        self.cell(0, 6, _safe_text(title), ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(6)

    def kv_rows(self, rows: list[tuple[str, str]], highlight_last: bool = False):
        row_h = 8
        for i, (label, value) in enumerate(rows):
            if self.get_y() + row_h > 280:
                self.add_page()
            y = self.get_y()
            fill = ROW_ALT if i % 2 == 0 else WHITE
            if highlight_last and i == len(rows) - 1:
                self.set_fill_color(220, 252, 231)
            else:
                self.set_fill_color(*fill)
            self.rect(MARGIN_L, y, self.content_w, row_h, style="F")
            self.set_xy(MARGIN_L + 5, y + 2)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*SLATE)
            self.cell(88, 5, _safe_text(label))
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*NAVY)
            self.cell(0, 5, _safe_text(value), ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def bullet_list(self, items: list[str]):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(55, 65, 81)
        for item in items:
            self.set_x(MARGIN_L + 4)
            self.multi_cell(self.content_w - 8, 5.5, f"  -  {_safe_text(item)}")
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def data_table(self, headers: list[str], widths: list[float], rows: list[list[str]]):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        y = self.get_y()
        x = MARGIN_L
        for h, w in zip(headers, widths):
            self.set_xy(x, y)
            self.cell(w, 8, h, border=0, fill=True)
            x += w
        self.ln(8)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(55, 65, 81)
        for i, row in enumerate(rows):
            if self.get_y() + 7 > 275:
                self.add_page()
                y = self.get_y()
                x = MARGIN_L
                self.set_font("Helvetica", "B", 8)
                self.set_fill_color(*NAVY)
                self.set_text_color(*WHITE)
                for h, w in zip(headers, widths):
                    self.set_xy(x, y)
                    self.cell(w, 8, h, fill=True)
                    x += w
                self.ln(8)
                self.set_font("Helvetica", "", 8)
                self.set_text_color(55, 65, 81)
            y = self.get_y()
            self.set_fill_color(*(ROW_ALT if i % 2 == 0 else WHITE))
            x = MARGIN_L
            for val, w in zip(row, widths):
                self.set_xy(x, y)
                self.cell(w, 7, _safe_text(str(val)[:40]), fill=True)
                x += w
            self.ln(7)
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def chart_block(
        self,
        png_bytes: bytes,
        caption: str,
        max_width: float | None = None,
        *,
        frame_pad: float = 8,
        max_height: float = 100,
    ):
        if max_width is None:
            max_width = self.content_w - 20
        try:
            from PIL import Image

            im = Image.open(BytesIO(png_bytes))
            w_px, h_px = im.size
            aspect = h_px / w_px if w_px else 0.65
        except Exception:
            aspect = 0.65

        img_w = max_width
        img_h = min(img_w * aspect, max_height)
        needed = img_h + frame_pad * 2 + 24
        if self.get_y() + needed > 272:
            self.add_page()

        self.ln(5)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SLATE)
        self.set_x(MARGIN_L + 4)
        self.cell(0, 5, _safe_text(caption), ln=True)
        self.ln(4)

        x = MARGIN_L + (self.content_w - img_w) / 2
        y = self.get_y()
        self.set_fill_color(*WHITE)
        self.set_draw_color(*BORDER)
        self.rect(x - frame_pad, y - frame_pad, img_w + 2 * frame_pad, img_h + 2 * frame_pad, style="DF")
        self.image(BytesIO(png_bytes), x=x, y=y, w=img_w, h=img_h)
        self.set_y(y + img_h + frame_pad + 12)


def _inr(val: float) -> str:
    return f"INR {val:,.0f}"


def _safe_text(text: str) -> str:
    """Helvetica in fpdf2 is latin-1; strip unsupported characters."""
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _fig_to_png(fig, *, pad: float = 0.35) -> bytes:
    buf = BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=150,
        bbox_inches="tight",
        facecolor="white",
        pad_inches=pad,
    )
    plt.close(fig)
    return buf.getvalue()


def _style_chart_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.tick_params(colors="#6b7280", labelsize=8)
    ax.set_facecolor("#fafafa")


def _spending_pie_png(cat_summary) -> bytes | None:
    if cat_summary is None or cat_summary.empty:
        return None
    chart_df = cat_summary[cat_summary["spend_amount"] > 0].copy()
    chart_df = chart_df[~chart_df["predicted_category"].isin(["Transfer"])]
    if chart_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    colors = CHART_COLORS[: len(chart_df)]
    wedges, _texts, autotexts = ax.pie(
        chart_df["spend_amount"],
        labels=None,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        pctdistance=0.68,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
        textprops={"fontsize": 8, "color": "#111827", "weight": "bold"},
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.legend(
        wedges,
        chart_df["predicted_category"].tolist(),
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=8,
        frameon=True,
        facecolor="white",
        edgecolor="#e5e7eb",
    )
    ax.set_title(
        "Spending mix (excl. transfer out)",
        fontsize=11,
        fontweight="bold",
        color="#111827",
        pad=16,
    )
    ax.set_aspect("equal")
    plt.subplots_adjust(left=0.02, right=0.68, top=0.88, bottom=0.1)
    return _fig_to_png(fig, pad=0.55)


def _forecast_line_png(monthly) -> bytes | None:
    if monthly is None or monthly.empty or "YearMonth" not in monthly.columns:
        return None

    plot_df = monthly.copy()
    plot_df["month"] = plot_df["YearMonth"].astype(str)
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    _style_chart_axes(ax)
    x = range(len(plot_df))
    if "Income_Amount" in plot_df.columns:
        ax.plot(x, plot_df["Income_Amount"], marker="o", lw=2, label="Income", color=CHART_COLORS[0])
    if "Expense_Amount" in plot_df.columns:
        ax.plot(x, plot_df["Expense_Amount"], marker="o", lw=2, label="Expense", color=CHART_COLORS[1])
    if "Net_Cash_Flow" in plot_df.columns:
        ax.plot(x, plot_df["Net_Cash_Flow"], marker="o", lw=2, label="Net", color=CHART_COLORS[2])
    ax.set_xticks(list(x))
    ax.set_xticklabels(plot_df["month"], rotation=32, ha="right", fontsize=7)
    ax.set_ylabel("Amount (INR)", fontsize=8, color="#6b7280")
    ax.legend(fontsize=8, frameon=True, facecolor="white", edgecolor="#e5e7eb")
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.set_title("Monthly cash flow", fontsize=11, fontweight="bold", color="#111827", pad=10)
    fig.tight_layout(pad=1.2)
    return _fig_to_png(fig)


def build_summary_pdf(
    file_names: list[str],
    txn_count: int,
    income_total: float,
    expense_total: float,
    net_total: float,
    transfer_out: float,
    transfer_in: float,
    risk_level: str,
    risk_score: int,
    risk_reasons: list[str],
    cat_summary,
    forecast_expense,
    forecast_income,
    forecast_net,
    forecast_note: str | None,
    monthly=None,
) -> bytes:
    pie_png = _spending_pie_png(cat_summary)
    line_png = _forecast_line_png(monthly)

    pdf = FinGuidePDF()
    pdf.add_page()
    pdf.meta_block(file_names)

    pdf.section_title("Financial overview")
    overview_rows = [
        ("Transactions parsed", f"{txn_count:,}"),
        ("Income (all credits)", _inr(income_total)),
        ("Expenses (excl. transfer out)", _inr(expense_total)),
        ("Transfers out (excluded from spend)", _inr(transfer_out)),
        ("Transfers in (included in income)", _inr(transfer_in)),
        ("Net cash flow", _inr(net_total)),
    ]
    pdf.kv_rows(overview_rows, highlight_last=True)

    pdf.section_title(f"Risk profile - {risk_level}")
    pdf.kv_rows([("Risk score", f"{risk_score} / 100")])
    if risk_reasons:
        pdf.bullet_list(risk_reasons)
    else:
        pdf.bullet_list(["No major flags in this period."])

    pdf.section_title("Spending by category")
    if cat_summary is None or cat_summary.empty:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(MARGIN_L + 4)
        pdf.cell(0, 6, "No expense categories available.", ln=True)
        pdf.ln(4)
    else:
        table_rows = []
        for _, row in cat_summary.head(14).iterrows():
            table_rows.append(
                [
                    str(row["predicted_category"]),
                    _inr(float(row["spend_amount"])),
                    f"{float(row['share_pct']):.1f}%",
                    str(int(row["txn_count"])),
                ]
            )
        col_w = [52, 48, 28, 22]
        pdf.data_table(
            ["Category", "Amount", "Share", "Rows"],
            col_w,
            table_rows,
        )

    if pie_png:
        pdf.chart_block(
            pie_png,
            "Figure 1 - Spending distribution",
            max_width=pdf.content_w - 24,
            frame_pad=10,
            max_height=108,
        )

    pdf.section_title("Forecast")
    if forecast_note:
        pdf.bullet_list([forecast_note])
    elif forecast_expense is not None:
        pdf.kv_rows(
            [
                ("Expected expense", _inr(forecast_expense)),
                ("Expected income", _inr(forecast_income)),
                ("Expected net cash flow", _inr(forecast_net)),
            ]
        )
    else:
        pdf.bullet_list(["Forecast not available for this upload."])

    if line_png:
        pdf.chart_block(
            line_png,
            "Figure 2 - Monthly cash flow history",
            frame_pad=8,
            max_height=88,
        )

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*SLATE)
    pdf.set_x(MARGIN_L)
    

    raw = pdf.output()
    return raw if isinstance(raw, bytes) else bytes(raw)
