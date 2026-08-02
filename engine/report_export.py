"""
engine/report_export.py

Generates a branded PDF version of a FraudScope scan report using
reportlab. Takes the same JSON shape returned by /api/scan and renders it
as a polished, downloadable document -- no data leaves the server to do
this (pure local rendering, consistent with FraudScope's privacy story).
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

# Brand colors (matched to static/css/style.css :root tokens)
NAVY = colors.HexColor("#0B0E14")
CYAN = colors.HexColor("#2DE1FC")
GREEN = colors.HexColor("#3DDC84")
AMBER = colors.HexColor("#FFB020")
RED = colors.HexColor("#FF4D4D")
MUTED = colors.HexColor("#8A93A6")
WHITE = colors.HexColor("#FFFFFF")

RISK_COLORS = {"high": RED, "medium": AMBER, "clear": GREEN, "med": AMBER}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="FSTitle",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=NAVY,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="FSMeta",
            fontName="Helvetica",
            fontSize=9,
            textColor=MUTED,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="FSSection",
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=NAVY,
            spaceBefore=18,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="FSBody",
            fontName="Helvetica",
            fontSize=9.5,
            textColor=colors.HexColor("#333333"),
            leading=13,
        )
    )
    styles.add(
        ParagraphStyle(
            name="FSFooter",
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        )
    )
    return styles


def _summary_table(scan_data: dict, styles) -> Table:
    total = scan_data.get("total_rows", 0)
    high = scan_data.get("high_risk", 0)
    medium = scan_data.get("medium_risk", 0)
    clear = scan_data.get("clear", 0)

    def cell(label, value, color):
        return Paragraph(
            f'<font color="{color.hexval()}" size="18"><b>{value}</b></font>'
            f'<br/><font size="8" color="#8A93A6">{label}</font>',
            styles["FSBody"],
        )

    data = [
        [
            cell("TOTAL SCANNED", total, NAVY),
            cell("HIGH RISK", high, RED),
            cell("MEDIUM RISK", medium, AMBER),
            cell("CLEAR", clear, GREEN),
        ]
    ]
    table = Table(data, colWidths=[1.6 * inch] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E2E5EA")),
                ("INNERGRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#E2E5EA")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _method_table(scan_data: dict, styles) -> Table:
    method_counts = scan_data.get("method_counts", {})
    header = ["Detection Method", "Flags"]
    rows = [[m.replace("_", " ").title(), str(c)] for m, c in method_counts.items()]
    data = [header] + rows

    table = Table(data, colWidths=[3.5 * inch, 1.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F5F6F8")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E5EA")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _transactions_table(scan_data: dict, styles) -> Table:
    rows = scan_data.get("rows", [])
    header = ["ID", "Vendor", "Amount", "Risk", "Reason"]
    data = [header]

    for r in rows:
        risk = str(r.get("risk", "")).lower()
        risk_color = RISK_COLORS.get(risk, MUTED)
        risk_label = Paragraph(
            f'<font color="{risk_color.hexval()}"><b>{risk.upper()}</b></font>',
            styles["FSBody"],
        )
        reason = Paragraph(str(r.get("reason", "")), styles["FSBody"])
        data.append(
            [
                str(r.get("id", "")),
                str(r.get("vendor", "")),
                str(r.get("amount", "")),
                risk_label,
                reason,
            ]
        )

    table = Table(
        data,
        colWidths=[0.7 * inch, 1.3 * inch, 1.0 * inch, 0.7 * inch, 2.8 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F5F6F8")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E5EA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def generate_pdf_report(scan_data: dict) -> io.BytesIO:
    """
    Build a branded PDF report from the same JSON shape /api/scan returns.

    Returns an in-memory BytesIO positioned at the start, ready to be sent
    as a file response.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )
    styles = _styles()
    story = []

    filename = scan_data.get("filename", "uploaded_ledger.csv")
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    story.append(Paragraph("FraudScope Scan Report", styles["FSTitle"]))
    story.append(
        Paragraph(
            f"Source file: {filename} &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {generated_at}",
            styles["FSMeta"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E5EA")))

    story.append(Paragraph("Summary", styles["FSSection"]))
    story.append(_summary_table(scan_data, styles))

    story.append(Paragraph("Detection Method Breakdown", styles["FSSection"]))
    story.append(_method_table(scan_data, styles))

    story.append(Paragraph("Flagged Transactions", styles["FSSection"]))
    story.append(_transactions_table(scan_data, styles))

    story.append(Spacer(1, 24))
    story.append(
        Paragraph(
            "Generated by FraudScope &mdash; all detection logic runs locally; "
            "no transaction data is sent to any third party to produce this report.",
            styles["FSFooter"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer