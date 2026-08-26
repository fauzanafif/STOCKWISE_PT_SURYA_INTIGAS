"""KPI cards for the currently filtered dataset — big, color-coded, and
labeled in plain Indonesian so the dashboard reads clearly at a glance."""
import streamlit as st

from utils.calculations import STATUS_TIDAK_AMAN
from utils.theme import COLOR_AMAN, COLOR_TIDAK_AMAN, COLOR_WARNING, SERIES_BLUE, SERIES_ORANGE

_CARD = """
<div class="sw-kpi-card">
    <div class="sw-kpi-icon" style="background:{accent}1a; color:{accent};">{icon}</div>
    <div class="sw-kpi-body">
        <div class="sw-kpi-label">{label}</div>
        <div class="sw-kpi-value" style="color:{accent};">{value}</div>
        <div class="sw-kpi-sub">{sub}</div>
    </div>
</div>
"""


def render_kpis(df):
    total_barang = len(df)
    barang_aman = int((df["Status"] != STATUS_TIDAK_AMAN).sum())
    barang_tidak_aman = int((df["Status"] == STATUS_TIDAK_AMAN).sum())
    total_stok = df["Sisa Stok"].sum()
    total_safety = df["Safety Stock"].sum()
    total_defisit = df["Defisit"].sum()
    health_pct = round((barang_aman / total_barang) * 100, 1) if total_barang else 0.0

    cards = [
        ("📦", "Total Barang", f"{total_barang:,}", "Jumlah kode barang aktif", SERIES_BLUE),
        ("✅", "Barang Aman", f"{barang_aman:,}", "Stok mencukupi safety stock", COLOR_AMAN),
        ("🚨", "Barang Tidak Aman", f"{barang_tidak_aman:,}", "Perlu perhatian / replenishment", COLOR_TIDAK_AMAN),
        ("🏬", "Total Stok", f"{total_stok:,.0f}", "Total unit tersedia di gudang", SERIES_BLUE),
        ("🛡️", "Total Safety Stock", f"{total_safety:,.0f}", "Total batas aman minimum", SERIES_ORANGE),
        (
            "📉",
            "Defisit Stok",
            f"{total_defisit:,.0f}",
            "Total kekurangan dari safety stock",
            COLOR_TIDAK_AMAN if total_defisit > 0 else COLOR_AMAN,
        ),
    ]

    html = ['<div class="sw-kpi-grid">']
    for icon, label, value, sub, accent in cards:
        html.append(_CARD.format(icon=icon, label=label, value=value, sub=sub, accent=accent))
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    if health_pct >= 80:
        bar_color, health_word = COLOR_AMAN, "Sehat"
    elif health_pct >= 50:
        bar_color, health_word = COLOR_WARNING, "Perlu Perhatian"
    else:
        bar_color, health_word = COLOR_TIDAK_AMAN, "Kritis"

    st.markdown(
        f"""
        <div class="sw-health">
          <div class="sw-health-label">
            <span>💡 Skor Kesehatan Inventory</span>
            <span class="sw-health-pct" style="color:{bar_color};">{health_pct}% Aman — {health_word}</span>
          </div>
          <div class="sw-health-track">
            <div class="sw-health-fill" style="width:{health_pct}%; background:{bar_color};"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
