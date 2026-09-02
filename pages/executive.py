"""Executive Dashboard — inventory, risk, and procurement on one screen."""
import plotly.graph_objects as go
import streamlit as st

from stockwise import queries
from stockwise.config import STATUS_COLORS, STATUS_LABELS
from stockwise.ui import attention_strip, fmt_num, kpi_grid, page_header, require_db, section

page_header("Executive Dashboard", "Kondisi inventory, risiko, dan procurement — satu layar.", icon="📦")
if not require_db():
    st.stop()
attention_strip()


@st.cache_data(show_spinner=False)
def _kpis(fp):
    return queries.executive_kpis()


@st.cache_data(show_spinner=False)
def _status_dist(fp):
    return queries.read_df("SELECT stock_status s, COUNT(*) c FROM v_inventory GROUP BY s ORDER BY c DESC")


@st.cache_data(show_spinner=False)
def _top_prio(fp):
    return queries.procurement_priority().head(10)


@st.cache_data(show_spinner="Menyusun laporan…")
def _pdf(fp):
    from stockwise.report import build_executive_pdf
    return build_executive_pdf()


fp = queries.data_fingerprint()
k = _kpis(fp)
health = k["stock_health"]

_hcol = st.columns([4, 1])[1]
_hcol.download_button("⬇️ Laporan PDF", _pdf(fp), file_name="stockwise_executive.pdf",
                      mime="application/pdf", width='stretch')

kpi_grid([
    ("Total Item", fmt_num(k["total_item"]), "kode barang di master", "#1f5fbf"),
    ("Total Sisa Stok", fmt_num(k["total_stok"]), "unit (item ber-stok terdata)", "#1f5fbf"),
    ("Tidak Aman", fmt_num(k["tidak_aman"]), "stok < safety stock", STATUS_COLORS["TIDAK_AMAN"]),
    ("Stok Habis", fmt_num(k["out_of_stock"]), "sisa = 0, SS > 0", STATUS_COLORS["OUT_OF_STOCK"]),
    ("Critical", fmt_num(k["critical"]), "defisit besar / prioritas tinggi", "#8a1c1c"),
    ("Total Defisit", fmt_num(k["total_defisit"]), "kekurangan vs safety stock", STATUS_COLORS["TIDAK_AMAN"]),
    ("Incoming (PPB)", fmt_num(k["incoming"]), "sudah dipesan, belum diterima", "#c98500"),
    ("Skor Kesehatan", f"{health}%" if health is not None else "—",
     f"AMAN / {fmt_num(k['assessable'])} item yang bisa dinilai", STATUS_COLORS["AMAN"]),
])

jump = st.columns(5)
_targets = [
    ("🔴 Tidak Aman", "TIDAK_AMAN"), ("⛔ Stok Habis", "OUT_OF_STOCK"),
    ("🟣 BEP", "BEP"), ("🟠 Belum ada SS", "NO_SAFETY_STOCK"), ("⚪ Stok belum terdata", "UNKNOWN"),
]
for col, (label, status) in zip(jump, _targets):
    if col.button(label, width='stretch'):
        st.session_state["inv_filter_status"] = status
        st.switch_page("pages/inventory.py")

if (k["ss_known"] or 0) < (k["total_item"] or 1) * 0.5:
    st.info(
        f"⚠️ Safety Stock baru tersedia untuk **{fmt_num(k['ss_known'])} dari {fmt_num(k['total_item'])}** item. "
        f"**{fmt_num(k['no_ss'])}** item belum bisa dinilai aman/tidak, "
        f"**{fmt_num(k['unknown_stok'])}** item sisa stoknya belum terdata. "
        "Angka risiko di bawah hanya mencakup item yang datanya lengkap — detail di Data Management → Data Quality."
    )

st.write("")
c1, c2 = st.columns([1.1, 1])
with c1:
    section("Sebaran status stok")
    dist = _status_dist(fp)
    if not dist.empty:
        dist["label"] = dist["s"].map(lambda x: STATUS_LABELS.get(x, x))
        fig = go.Figure(go.Bar(
            x=dist["c"], y=dist["label"], orientation="h",
            marker_color=[STATUS_COLORS.get(s, "#888") for s in dist["s"]],
            text=dist["c"], textposition="auto",
        ))
        fig.update_layout(height=300, margin=dict(l=6, r=6, t=6, b=6),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          xaxis_title="Jumlah item", yaxis_title="")
        st.plotly_chart(fig, width='stretch')
with c2:
    section("Procurement outstanding")
    st.metric("PPB belum selesai", fmt_num(k["ppb_outstanding"]))
    st.metric("PO belum lengkap diterima", fmt_num(k["po_outstanding"]))
    st.metric("RI 30 hari terakhir", fmt_num(k["ri_30d"]))
    st.page_link("pages/procurement.py", label="Buka Procurement Priority", icon="🚚")

st.write("")
section("10 item paling mendesak")
prio = _top_prio(fp)
if prio.empty:
    st.success("Tidak ada item yang butuh aksi procurement segera (berdasarkan data yang lengkap).")
else:
    show = prio[["kode_barang", "deskripsi", "sisa_stok", "safety_stock", "defisit",
                 "lead_time_days", "incoming_qty", "projected_stock", "priority_level", "rekomendasi"]].copy()
    show.columns = ["Kode", "Deskripsi", "Sisa", "Safety", "Defisit", "Lead Time",
                    "Incoming", "Projected", "Priority", "Rekomendasi"]
    st.dataframe(show, width='stretch', hide_index=True)
    st.page_link("pages/inventory.py", label="Lihat semua item di Inventory", icon="📋")
