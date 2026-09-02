"""STOCKWISE — Executive Dashboard (entry point for the multi-source system).

Run:  streamlit run Home.py
The legacy single-Excel dashboard still lives at app.py (streamlit run app.py).
"""
import plotly.graph_objects as go
import streamlit as st

from stockwise import queries
from stockwise.config import STATUS_COLORS, STATUS_LABELS
from stockwise.ui import fmt_num, kpi_grid, page_header, require_db

page_header("Executive Dashboard", "Kondisi inventory, risiko, dan procurement — satu layar.", icon="📦")

if not require_db():
    st.page_link("pages/7_🗄️_Data_Management.py", label="→ Buka Data Management untuk upload Excel", icon="🗄️")
    st.stop()


@st.cache_data(show_spinner=False)
def _kpis(fp):
    return queries.executive_kpis()


fp = queries.data_fingerprint()
k = _kpis(fp)

health = k["stock_health"]
kpi_grid([
    ("Total Item", fmt_num(k["total_item"]), "kode barang di master", "#2a78d6"),
    ("Total Sisa Stok", fmt_num(k["total_stok"]), "unit (item ber-stok terdata)", "#2a78d6"),
    ("Tidak Aman", fmt_num(k["tidak_aman"]), "stok < safety stock", STATUS_COLORS["TIDAK_AMAN"]),
    ("Stok Habis", fmt_num(k["out_of_stock"]), "sisa = 0, SS > 0", STATUS_COLORS["OUT_OF_STOCK"]),
    ("Critical", fmt_num(k["critical"]), "defisit besar / prioritas tinggi", "#8a1c1c"),
    ("Total Defisit", fmt_num(k["total_defisit"]), "kekurangan vs safety stock", STATUS_COLORS["TIDAK_AMAN"]),
    ("Incoming (PPB)", fmt_num(k["incoming"]), "sudah dipesan, belum diterima", "#c98500"),
    ("Skor Kesehatan", f"{health}%" if health is not None else "—",
     f"AMAN / {fmt_num(k['ss_known'])} item ber-SS", STATUS_COLORS["AMAN"]),
])

if (k["ss_known"] or 0) < (k["total_item"] or 1) * 0.5:
    st.info(
        f"⚠️ Safety Stock baru tersedia untuk **{fmt_num(k['ss_known'])} dari {fmt_num(k['total_item'])}** item "
        f"(sumber: 13 sheet `SAFETY STOCK *`). **{fmt_num(k['no_ss'])}** item belum bisa dinilai aman/tidak, "
        f"**{fmt_num(k['unknown_stok'])}** item sisa stoknya belum terdata. "
        "Angka risiko di bawah hanya mencakup item yang datanya lengkap — lihat Data Management → Data Quality."
    )

st.divider()
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("#### Sebaran status stok")
    dist = queries.read_df(
        "SELECT stock_status s, COUNT(*) c FROM v_inventory GROUP BY s ORDER BY c DESC"
    )
    if not dist.empty:
        dist["label"] = dist["s"].map(lambda x: STATUS_LABELS.get(x, x))
        fig = go.Figure(go.Bar(
            x=dist["c"], y=dist["label"], orientation="h",
            marker_color=[STATUS_COLORS.get(s, "#888") for s in dist["s"]],
            text=dist["c"], textposition="auto",
        ))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis_title="Jumlah item", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("#### Procurement outstanding")
    st.metric("PPB belum selesai", fmt_num(k["ppb_outstanding"]))
    st.metric("PO belum lengkap diterima", fmt_num(k["po_outstanding"]))
    st.metric("RI 30 hari terakhir", fmt_num(k["ri_30d"]))
    st.page_link("pages/2_🚚_Procurement.py", label="Buka Procurement Priority", icon="🚚")

st.divider()
st.markdown("#### 10 item paling mendesak (Critical / Priority Score tertinggi)")
prio = queries.procurement_priority().head(10)
if prio.empty:
    st.success("Tidak ada item yang butuh aksi procurement segera (berdasarkan data yang lengkap).")
else:
    show = prio[["kode_barang", "deskripsi", "sisa_stok", "safety_stock", "defisit",
                 "lead_time_days", "incoming_qty", "projected_stock", "priority_level", "rekomendasi"]].copy()
    show.columns = ["Kode", "Deskripsi", "Sisa", "Safety", "Defisit", "Lead Time",
                    "Incoming", "Projected", "Priority", "Rekomendasi"]
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.page_link("pages/1_📦_Inventory.py", label="Lihat semua item di Inventory", icon="📦")

st.divider()
cols = st.columns(4)
nav = [
    ("pages/1_📦_Inventory.py", "Inventory", "📦"),
    ("pages/2_🚚_Procurement.py", "Procurement", "🚚"),
    ("pages/3_📉_Usage_Analysis.py", "Usage Analysis", "📉"),
    ("pages/4_📍_Tracking.py", "Tracking", "📍"),
]
for c, (path, label, icon) in zip(cols, nav):
    c.page_link(path, label=label, icon=icon)
