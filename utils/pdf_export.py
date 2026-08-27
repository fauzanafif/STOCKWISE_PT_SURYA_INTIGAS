"""PDF export: a printable inventory report built with reportlab (pure Python,
no external binary like wkhtmltopdf/weasyprint needs).

Unlike the Excel/CSV export (full data, every column, for further processing),
this is a print-friendly *report*: a KPI summary, a compact item table, and a
Procurement Priority appendix — mirroring what's already on the Dashboard and
Procurement tabs, laid out for A4 landscape instead of a spreadsheet.
"""
import html
import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from utils.calculations import STATUS_AMAN, STATUS_BEP, STATUS_TIDAK_AMAN
from utils.theme import COLOR_AMAN, COLOR_BEP, COLOR_TIDAK_AMAN, COLOR_WARNING

BLUE_DARK = "#14328c"
BLUE_TINT = "#eef4fc"
GRID_BLUE = "#c7d6ef"
ROW_TINT = "#f5f8fd"
MUTED = "#5b6b8c"

STATUS_HEX = {STATUS_AMAN: COLOR_AMAN, STATUS_TIDAK_AMAN: COLOR_TIDAK_AMAN, STATUS_BEP: COLOR_BEP}
PRIORITY_HEX = {"HIGH": COLOR_TIDAK_AMAN, "MEDIUM": COLOR_WARNING, "LOW": COLOR_AMAN}

# (column name, width) — kept narrow enough to fit landscape A4 at ~7.5pt.
ITEM_COLUMNS = [
    ("Kode Barang", 24 * mm),
    ("Deskripsi Barang", 55 * mm),
    ("Kategori Induk", 28 * mm),
    ("Letak Gudang", 20 * mm),
    ("UoM", 12 * mm),
    ("Safety Stock", 16 * mm),
    ("Sisa Stok", 16 * mm),
    ("Selisih", 16 * mm),
    ("Status", 20 * mm),
]

PROCUREMENT_COLUMNS = [
    ("Kode Barang", 22 * mm),
    ("Deskripsi Barang", 50 * mm),
    ("Letak Gudang", 20 * mm),
    ("Safety Stock", 15 * mm),
    ("Sisa Stok", 15 * mm),
    ("Defisit", 15 * mm),
    ("Lead Time", 15 * mm),
    ("Priority Score", 18 * mm),
    ("Priority Level", 18 * mm),
    ("Rekomendasi", 65 * mm),
]


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SWTitle", parent=styles["Title"], textColor=colors.HexColor(BLUE_DARK), fontSize=18, spaceAfter=2))
    styles.add(ParagraphStyle("SWSubtitle", parent=styles["Normal"], textColor=colors.HexColor(MUTED), fontSize=9, spaceAfter=10))
    styles.add(ParagraphStyle("SWSection", parent=styles["Heading2"], textColor=colors.HexColor(BLUE_DARK), fontSize=13, spaceBefore=14, spaceAfter=6))
    styles.add(ParagraphStyle("SWCell", parent=styles["Normal"], fontSize=7.5, leading=9))
    styles.add(ParagraphStyle("SWCellBold", parent=styles["SWCell"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("SWHeaderCell", parent=styles["SWCell"], textColor=colors.white, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("SWKpiLabel", parent=styles["SWCellBold"], alignment=TA_CENTER))
    styles.add(ParagraphStyle("SWKpiValue", parent=styles["SWCell"], fontSize=12, fontName="Helvetica-Bold", textColor=colors.HexColor(BLUE_DARK), alignment=TA_CENTER))
    return styles


def _format_value(value) -> str:
    """Stringify a cell value for display, escaping it for use inside a
    reportlab Paragraph (which parses a small HTML-like markup subset, so raw
    '&'/'<'/'>' in a product description would otherwise break rendering).
    """
    if isinstance(value, float):
        text = f"{value:,.0f}"
    elif value is None:
        text = ""
    else:
        text = str(value)
    return html.escape(text)


def _kpi_table(df: pd.DataFrame, styles) -> Table:
    total = len(df)
    aman = int((df["Status"] == STATUS_AMAN).sum())
    tidak_aman = int((df["Status"] == STATUS_TIDAK_AMAN).sum())
    bep = int((df["Status"] == STATUS_BEP).sum())
    total_stok = df["Sisa Stok"].sum()
    total_safety = df["Safety Stock"].sum()
    total_defisit = df["Defisit"].sum()
    health = round((aman / total) * 100, 1) if total else 0.0

    labels = [
        "Total Barang", "Barang Aman", "Barang Tidak Aman", "Barang BEP",
        "Total Stok", "Total Safety Stock", "Defisit Stok", "Skor Kesehatan",
    ]
    values = [
        f"{total:,}", f"{aman:,}", f"{tidak_aman:,}", f"{bep:,}",
        f"{total_stok:,.0f}", f"{total_safety:,.0f}", f"{total_defisit:,.0f}", f"{health}%",
    ]

    header_row = [Paragraph(label, styles["SWKpiLabel"]) for label in labels]
    value_row = [Paragraph(value, styles["SWKpiValue"]) for value in values]

    table = Table([header_row, value_row])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_TINT)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(GRID_BLUE)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _item_table(df: pd.DataFrame, columns: list, styles, color_maps: dict = None) -> Table:
    """Build a paginated item table. `color_maps` is {column_name: {value: hex_color}}
    to bold+color-code specific cells (e.g. Status, Priority Level) — done via
    per-value Paragraph styles, since a plain TableStyle TEXTCOLOR command has
    no effect on cells that hold a Paragraph flowable rather than a bare string.
    """
    color_maps = color_maps or {}
    colored_styles = {}
    for value_map in color_maps.values():
        for hexcolor in value_map.values():
            if hexcolor not in colored_styles:
                colored_styles[hexcolor] = ParagraphStyle(
                    f"SWCell_{hexcolor.lstrip('#')}",
                    parent=styles["SWCell"],
                    textColor=colors.HexColor(hexcolor),
                    fontName="Helvetica-Bold",
                )

    header = [Paragraph(name, styles["SWHeaderCell"]) for name, _ in columns]
    widths = [w for _, w in columns]
    rows = [header]
    for _, row in df.iterrows():
        cells = []
        for name, _ in columns:
            raw_value = row.get(name, "")
            cell_style = styles["SWCell"]
            value_map = color_maps.get(name)
            if value_map:
                hexcolor = value_map.get(raw_value)
                if hexcolor:
                    cell_style = colored_styles[hexcolor]
            cells.append(Paragraph(_format_value(raw_value), cell_style))
        rows.append(cells)

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_DARK)),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(GRID_BLUE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(ROW_TINT)]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def build_pdf_bytes(df: pd.DataFrame, scope_label: str, file_name: str = "") -> bytes:
    """Build the full PDF report and return its bytes.

    `df` should already be the recalculated, scope-selected dataset (full or
    filtered — the caller decides which, same as the Excel/CSV export).
    """
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="STOCKWISE - Laporan Inventory",
    )

    subtitle_bits = [scope_label, f"{len(df):,} barang"]
    if file_name:
        subtitle_bits.append(html.escape(file_name))
    subtitle_bits.append(f"Dibuat {datetime.now().strftime('%d %B %Y %H:%M')}")

    unsafe = df[df["Status"] == STATUS_TIDAK_AMAN].sort_values("Priority Score", ascending=False)

    story = [
        Paragraph("STOCKWISE — Laporan Inventory", styles["SWTitle"]),
        Paragraph(" • ".join(subtitle_bits), styles["SWSubtitle"]),
        _kpi_table(df, styles),
        Spacer(1, 16),
        Paragraph("Daftar Barang", styles["SWSection"]),
        _item_table(df, ITEM_COLUMNS, styles, color_maps={"Status": STATUS_HEX}),
        Spacer(1, 16),
        Paragraph(f"Procurement Priority ({len(unsafe):,} barang perlu aksi)", styles["SWSection"]),
    ]
    if unsafe.empty:
        story.append(Paragraph("Tidak ada barang yang memerlukan procurement segera.", styles["SWSubtitle"]))
    else:
        story.append(_item_table(unsafe, PROCUREMENT_COLUMNS, styles, color_maps={"Priority Level": PRIORITY_HEX}))

    doc.build(story)
    return buffer.getvalue()
