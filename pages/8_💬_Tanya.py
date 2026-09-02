"""Ask STOCKWISE — jawaban cepat untuk pertanyaan manajemen, bisa ditelusuri ke sumber.

Rule-based (tanpa LLM): kenali bentuk pertanyaan → jalankan query yang cocok.
"""
import streamlit as st

from utils import queries
from utils.sw_config import STATUS_LABELS
from utils.database import read_df, scalar
from utils.dashboard_ui import fmt_num, page_header, require_db, status_badge

page_header("Tanya STOCKWISE", "Pertanyaan yang sering muncul di rapat — jawaban langsung dari data.", icon="💬")
if not require_db():
    st.stop()

mode = st.radio("Mode", ["📋 Pertanyaan umum", "🔎 Tanya satu barang"], horizontal=True, label_visibility="collapsed")
st.divider()

# ────────────────────────────── satu barang ──────────────────────────────
if mode.startswith("🔎"):
    opts = queries.read_df(
        "SELECT id, COALESCE(kode_barang,'(no kode)') || ' — ' || deskripsi AS label FROM master_items ORDER BY deskripsi")
    pick = st.selectbox("Barang", opts["label"], index=None, placeholder="Ketik kode atau nama barang…")
    if not pick:
        st.info("Pilih barang di atas untuk lihat: sisa stok, safety stock, defisit, status PPB/PO/RI, pemakaian.")
        st.stop()
    item_id = opts.loc[opts["label"] == pick, "id"].iloc[0]
    d = queries.item_detail(item_id)
    m, c = d["master"], d["calc"]
    st.markdown(f"### {m['deskripsi']}")
    if c:
        st.markdown(status_badge(c["stock_status"]), unsafe_allow_html=True)
        a, b, e, f = st.columns(4)
        a.metric("Sisa Stok", "belum terdata" if not c["sisa_stok_known"] else fmt_num(c["sisa_stok"]))
        b.metric("Safety Stock", "—" if not c["safety_stock_known"] else fmt_num(c["safety_stock"]))
        e.metric("Defisit", fmt_num(c["defisit"]))
        f.metric("Priority", c["priority_level"])
        g, h, i = st.columns(3)
        g.metric("Incoming (PPB blm diterima)", fmt_num(c["incoming_qty"]))
        h.metric("Projected Stock", fmt_num(c["projected_stock"]))
        i.metric("Rata-rata pakai/bln", fmt_num(c["avg_monthly_usage"]))
        st.info(f"**Rekomendasi:** {c['rekomendasi']}")
    ppb, ri, npbg = d["ppb"], d["ri"], d["npbg"]
    st.markdown(
        f"- **Sudah PPB?** {'Ya — ' + str(ppb['no_ppb'].nunique()) + ' PPB' if not ppb.empty else 'Belum ada PPB terhubung'}"
        + (f" (terbaru: {ppb.iloc[0]['no_ppb']}, status {ppb.iloc[0]['status']})" if not ppb.empty else "")
    )
    st.markdown(
        f"- **Sudah PO / diterima?** {'Ya — ' + str(ri['no_ri'].nunique()) + ' RI, total diterima ' + fmt_num(ri['qty'].sum()) if not ri.empty else 'Belum ada RI'}"
        + (f", vendor {', '.join(v for v in ri['vendor'].dropna().unique()[:3])}" if not ri.empty else "")
    )
    if not ppb.empty:
        out = max(ppb["qty"].sum() - (ri["qty"].sum() if not ri.empty else 0), 0)
        st.markdown(f"- **Outstanding (PPB − RI):** {fmt_num(out)}")
    st.markdown(f"- **Total pemakaian (NPBG):** {fmt_num(npbg['qty'].sum()) if not npbg.empty else 0}"
                + (f" dalam {npbg['no_npbg'].nunique()} dokumen" if not npbg.empty else ""))
    st.page_link("pages/4_🔎_Detail_Barang.py", label="Buka Item Detail lengkap →", icon="🔍")
    st.session_state["detail_item_id"] = item_id
    st.stop()

# ────────────────────────────── pertanyaan umum ──────────────────────────────
PRESETS = {
    "Berapa total sisa stok & kesehatan inventory?": "overview",
    "Barang apa yang stoknya habis?": "oos",
    "Barang mana yang tidak aman / harus dibeli duluan?": "unsafe",
    "PPB mana yang belum selesai?": "ppb_open",
    "PO mana yang belum lengkap diterima?": "po_open",
    "Barang apa yang paling banyak dipakai?": "top_usage",
    "Divisi mana paling banyak menggunakan barang?": "by_divisi",
    "Pelanggan / proyek mana yang paling banyak?": "by_customer",
    "Barang apa yang dipinjam & belum kembali?": "borrow",
    "Kendaraan apa yang sedang maintenance?": "maint",
    "Barang apa yang dipakai untuk manufaktur/assembly?": "mfg",
}
kind = PRESETS[st.selectbox("Pertanyaan", list(PRESETS))]
st.write("")

if kind == "overview":
    k = queries.executive_kpis()
    st.markdown(
        f"- Total item: **{fmt_num(k['total_item'])}** · total sisa stok (terdata): **{fmt_num(k['total_stok'])}**\n"
        f"- Tidak aman **{fmt_num(k['tidak_aman'])}** · stok habis **{fmt_num(k['out_of_stock'])}** · critical **{fmt_num(k['critical'])}**\n"
        f"- Skor kesehatan **{k['stock_health']}%** (dari {fmt_num(k['assessable'])} item yang datanya lengkap)\n"
        f"- Belum ada Safety Stock: **{fmt_num(k['no_ss'])}** · sisa stok belum terdata: **{fmt_num(k['unknown_stok'])}**"
    )
    st.page_link("app.py", label="→ Dashboard utama", icon="📦")

elif kind == "oos":
    df = queries.inventory_table(status=["OUT_OF_STOCK"])
    st.markdown(f"**{len(df)}** barang stoknya 0 (dengan safety stock > 0):")
    st.dataframe(df[["kode_barang", "deskripsi", "safety_stock", "lead_time_days", "priority_level"]],
                 width='stretch', hide_index=True)

elif kind == "unsafe":
    df = queries.procurement_priority()
    st.markdown(f"**{len(df)}** barang di bawah safety stock, urut prioritas:")
    st.dataframe(df[["kode_barang", "deskripsi", "sisa_stok", "safety_stock", "defisit",
                     "incoming_qty", "projected_stock", "priority_level", "rekomendasi"]].head(100),
                 width='stretch', hide_index=True)
    st.page_link("pages/1_🚚_Procurement.py", label="→ Procurement", icon="🚚")

elif kind == "ppb_open":
    df = read_df(
        "SELECT no_ppb, MIN(tgl_ppb) tgl, MAX(status) status, COUNT(*) item, SUM(qty) qty_ppb, "
        "(SELECT COALESCE(SUM(qty),0) FROM ri_lines r WHERE r.no_ppb=p.no_ppb) qty_ri "
        "FROM ppb_lines p WHERE LOWER(COALESCE(status,'')) NOT IN ('completed','close','error') "
        "GROUP BY no_ppb ORDER BY tgl DESC")
    st.markdown(f"**{len(df)}** PPB belum selesai:")
    st.dataframe(df, width='stretch', hide_index=True)

elif kind == "po_open":
    df = read_df(
        """SELECT p.no_po, p.vendor, p.total_qty qty_po,
                  (SELECT COALESCE(SUM(qty),0) FROM ri_lines r WHERE r.no_po=p.no_po) qty_diterima,
                  p.last_ri_date
           FROM po_derived p
           WHERE p.total_qty > (SELECT COALESCE(SUM(qty),0) FROM ri_lines r WHERE r.no_po=p.no_po)
           ORDER BY p.last_ri_date DESC""")
    st.markdown(f"**{len(df)}** PO belum lengkap diterima:")
    st.dataframe(df, width='stretch', hide_index=True)

elif kind == "top_usage":
    st.dataframe(queries.usage_summary()["top_items"], width='stretch', hide_index=True)
    st.page_link("pages/2_📉_Pemakaian.py", label="→ Usage Analysis", icon="📉")

elif kind == "by_divisi":
    st.dataframe(queries.usage_summary()["by_divisi"], width='stretch', hide_index=True)

elif kind == "by_customer":
    u = queries.usage_summary()
    c1, c2 = st.columns(2)
    c1.dataframe(u["by_pelanggan"], width='stretch', hide_index=True)
    c2.dataframe(read_df("SELECT nama_proyek, SUM(qty) qty FROM npbg_lines WHERE nama_proyek IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 30"),
                 width='stretch', hide_index=True)

elif kind == "borrow":
    df = read_df(
        "SELECT arah, tgl_pinjam, deskripsi, qty, pihak, keperluan, status, ref_keluar FROM borrow_lend "
        "WHERE UPPER(COALESCE(status,'')) NOT LIKE '%KEMBALI%' AND UPPER(COALESCE(status,'')) NOT LIKE '%LUNAS%' "
        "ORDER BY tgl_pinjam DESC")
    st.markdown(f"**{len(df)}** transaksi pinjam yang belum ditandai kembali/lunas:")
    st.dataframe(df, width='stretch', hide_index=True)

elif kind == "maint":
    df = read_df(
        "SELECT no_spk, sub_spk, nopol, tgl_laporan, keterangan_awal, bengkel, status, ref_npbg "
        "FROM asset_maintenance WHERE UPPER(COALESCE(status,'')) <> 'COMPLETED' ORDER BY tgl_laporan DESC")
    st.markdown(f"**{len(df)}** pekerjaan maintenance kendaraan belum selesai:")
    st.dataframe(df, width='stretch', hide_index=True)

elif kind == "mfg":
    df = read_df(
        "SELECT jenis, no_dok, hasil_produk, no_seri, proses, status, ref_npbg, ref_ri, tgl "
        "FROM manufacturing ORDER BY tgl DESC LIMIT 200")
    st.markdown("Material yang dipakai tercatat di NPBG yang terhubung (`ref_npbg`):")
    st.dataframe(df, width='stretch', hide_index=True)

st.caption("Semua jawaban dihitung dari stockwise.db oleh calculation engine — bisa ditelusuri ke baris Excel lewat Item Detail.")
