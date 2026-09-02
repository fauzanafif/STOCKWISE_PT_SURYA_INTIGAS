"""Executive PDF report for STOCKWISE v2 — built with ReportLab (pure Python).

A curated print report, not a data dump: KPI summary, stock-status breakdown,
Critical items, and the Procurement Priority list. Mirrors the dashboard.
"""
from __future__ import annotations

import html
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from utils import queries
from utils.sw_config import STATUS_LABELS

BLUE_D = "#12306f"
TINT = "#eef3fb"
GRID = "#c7d6ef"
ROW = "#f6f9fd"
MUTED = "#5c6b86"

STATUS_HEX = {
    "AMAN": "#0ca30c", "TIDAK_AMAN": "#d03b3b", "OUT_OF_STOCK": "#8a1c1c",
    "BEP": "#8a63d2", "NO_SAFETY_STOCK": "#c98500", "UNKNOWN": "#8a8a8a",
}
PRIO_HEX = {"HIGH": "#d03b3b", "MEDIUM": "#c98500", "LOW": "#0ca30c"}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("T", parent=s["Title"], textColor=colors.HexColor(BLUE_D), fontSize=17, spaceAfter=2))
    s.add(ParagraphStyle("Sub", parent=s["Normal"], textColor=colors.HexColor(MUTED), fontSize=8.5, spaceAfter=10))
    s.add(ParagraphStyle("H", parent=s["Heading2"], textColor=colors.HexColor(BLUE_D), fontSize=12, spaceBefore=13, spaceAfter=5))
    s.add(ParagraphStyle("C", parent=s["Normal"], fontSize=7.5, leading=9.5))
    s.add(ParagraphStyle("CH", parent=s["C"], textColor=colors.white, fontName="Helvetica-Bold"))
    s.add(ParagraphStyle("KL", parent=s["C"], fontName="Helvetica-Bold", alignment=1))
    s.add(ParagraphStyle("KV", parent=s["C"], fontSize=12, fontName="Helvetica-Bold",
                         textColor=colors.HexColor(BLUE_D), alignment=1))
    return s


def _esc(v) -> str:
    if v is None:
        return ""
    try:
        import math
        if isinstance(v, float):
            if math.isnan(v):
                return ""
            return html.escape(f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}")
    except (TypeError, ValueError):
        pass
    return html.escape(str(v))


def _kpi_table(k, s):
    labels = ["Total Item", "Total Sisa Stok", "Tidak Aman", "Stok Habis",
              "Critical", "Total Defisit", "Incoming", "Skor Kesehatan"]
    vals = [k["total_item"], k["total_stok"], k["tidak_aman"], k["out_of_stock"],
            k["critical"], k["total_defisit"], k["incoming"],
            f"{k['stock_health']}%" if k["stock_health"] is not None else "-"]
    t = Table([[Paragraph(x, s["KL"]) for x in labels],
               [Paragraph(_esc(v), s["KV"]) for v in vals]])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TINT)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(GRID)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _tbl(df, columns, s, color_col=None, color_map=None):
    head = [Paragraph(lbl, s["CH"]) for _, lbl, _ in columns]
    widths = [w for _, _, w in columns]
    styles_by_hex = {}
    if color_map:
        for hx in color_map.values():
            styles_by_hex[hx] = ParagraphStyle("c" + hx.lstrip("#"), parent=s["C"],
                                               textColor=colors.HexColor(hx), fontName="Helvetica-Bold")
    rows = [head]
    for _, r in df.iterrows():
        cells = []
        for key, _, _ in columns:
            val = r.get(key, "")
            cs = s["C"]
            if color_col == key and color_map and str(val) in color_map:
                cs = styles_by_hex[color_map[str(val)]]
            disp = STATUS_LABELS.get(str(val), val) if key == "stock_status" else val
            cells.append(Paragraph(_esc(disp), cs))
        rows.append(cells)
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE_D)),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(GRID)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(ROW)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_executive_pdf() -> bytes:
    s = _styles()
    k = queries.executive_kpis()
    dist = queries.read_df("SELECT stock_status, COUNT(*) n FROM v_inventory GROUP BY 1 ORDER BY n DESC")
    crit = queries.inventory_table(only_critical=True).head(40)
    prio = queries.procurement_priority().head(60)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title="STOCKWISE - Laporan Executive")
    story = [
        Paragraph("STOCKWISE — Laporan Executive", s["T"]),
        Paragraph(f"PT Surya Inti Gas · dibuat {datetime.now().strftime('%d %B %Y %H:%M')} · "
                  f"Skor kesehatan dari {_esc(k['assessable'])} item yang datanya lengkap", s["Sub"]),
        _kpi_table(k, s),
        Spacer(1, 6),
        Paragraph("Sebaran status stok", s["H"]),
        _tbl(dist.assign(label=dist["stock_status"]).rename(columns={"stock_status": "stock_status"}),
             [("stock_status", "Status", 55 * mm), ("n", "Jumlah item", 30 * mm)], s),
        Paragraph(f"Item Critical ({len(crit)} teratas)", s["H"]),
    ]
    if crit.empty:
        story.append(Paragraph("Tidak ada.", s["Sub"]))
    else:
        story.append(_tbl(crit, [
            ("kode_barang", "Kode", 22 * mm), ("deskripsi", "Deskripsi", 78 * mm),
            ("letak_gudang", "Gudang", 20 * mm), ("sisa_stok", "Sisa", 16 * mm),
            ("safety_stock", "Safety", 16 * mm), ("defisit", "Defisit", 16 * mm),
            ("lead_time_days", "LT", 12 * mm), ("priority_level", "Priority", 18 * mm),
        ], s, color_col="priority_level", color_map=PRIO_HEX))

    story.append(Paragraph(f"Procurement Priority ({len(prio)} teratas)", s["H"]))
    if prio.empty:
        story.append(Paragraph("Tidak ada barang yang perlu procurement segera.", s["Sub"]))
    else:
        story.append(_tbl(prio, [
            ("kode_barang", "Kode", 20 * mm), ("deskripsi", "Deskripsi", 62 * mm),
            ("sisa_stok", "Sisa", 14 * mm), ("safety_stock", "Safety", 14 * mm),
            ("defisit", "Defisit", 14 * mm), ("incoming_qty", "Incoming", 16 * mm),
            ("projected_stock", "Projected", 16 * mm), ("priority_level", "Priority", 16 * mm),
            ("rekomendasi", "Rekomendasi", 60 * mm),
        ], s, color_col="priority_level", color_map=PRIO_HEX))

    doc.build(story)
    return buf.getvalue()
