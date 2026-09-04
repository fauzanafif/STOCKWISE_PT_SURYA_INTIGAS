"""KPI cards for the currently filtered dataset — big, color-coded, and
labeled in plain Indonesian so the dashboard reads clearly at a glance."""
import streamlit as st

from utils.calculations import STATUS_AMAN, STATUS_BEP, STATUS_TIDAK_AMAN
from utils.theme import COLOR_AMAN, COLOR_BEP, COLOR_TIDAK_AMAN, COLOR_WARNING, SERIES_BLUE, SERIES_ORANGE

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
    barang_aman = int((df["Status"] == STATUS_AMAN).sum())
    barang_tidak_aman = int((df["Status"] == STATUS_TIDAK_AMAN).sum())
    barang_bep = int((df["Status"] == STATUS_BEP).sum())
    stok_habis = int((df["Sisa Stok"].fillna(0) == 0).sum())
    total_stok = df["Sisa Stok"].sum()
    total_safety = df["Safety Stock"].sum()
    total_defisit = df["Defisit"].sum()
    # Skor kesehatan menghitung BEP sebagai "aman" juga (barang tanpa kebijakan
    # stok bukan berarti bermasalah seperti TIDAK AMAN) — beda dari kartu
    # "Barang Aman" di atas, yang tetap Status == AMAN murni.
    health_pct = round(((barang_aman + barang_bep) / total_barang) * 100, 1) if total_barang else 0.0

    # Urutan sengaja: identitas → 4 kelompok status → 3 angka kuantitas.
    cards = [
        ("📦", "Total Barang", f"{total_barang:,}", "jenis barang terdaftar", SERIES_BLUE),
        ("✅", "Barang Aman", f"{barang_aman:,}", "stok cukup dari batas aman", COLOR_AMAN),
        ("🛒", "Perlu Dibeli", f"{barang_tidak_aman:,}", "stok di bawah batas aman", COLOR_TIDAK_AMAN),
        ("⛔", "Stok Habis", f"{stok_habis:,}", "sisa stok = 0",
         COLOR_TIDAK_AMAN if stok_habis else COLOR_AMAN),
        ("🎯", "Barang BEP", f"{barang_bep:,}", "belum ada kebijakan stok", COLOR_BEP),
        ("🏬", "Total Stok", f"{total_stok:,.0f}", "unit tersedia di gudang", SERIES_BLUE),
        ("🛡️", "Total Batas Aman", f"{total_safety:,.0f}", "gabungan seluruh safety stock", SERIES_ORANGE),
        (
            "📉",
            "Total Kekurangan",
            f"{total_defisit:,.0f}",
            "unit di bawah batas aman",
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
            <span>💚 Kondisi Stok Keseluruhan</span>
            <span class="sw-health-pct" style="color:{bar_color};">{health_pct}% Aman — {health_word}</span>
          </div>
          <div class="sw-health-track">
            <div class="sw-health-fill" style="width:{health_pct}%; background:{bar_color};"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
