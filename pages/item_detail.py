"""Item Detail — 360° view of one item: stock, procurement, usage, tracking, blueprint, lineage."""
import plotly.express as px
import streamlit as st

from stockwise import queries
from stockwise.config import STATUS_LABELS
from stockwise.ui import fmt_num, lineage, nice, page_header, require_db, status_badge

page_header("Item Detail", icon="🔍")
if not require_db():
    st.stop()

item_id = st.session_state.get("detail_item_id")

@st.cache_data(show_spinner=False)
def _item_options(fp):
    return queries.read_df(
        "SELECT id, COALESCE(kode_barang,'(no kode)') || ' — ' || deskripsi AS label "
        "FROM master_items ORDER BY deskripsi")


# allow direct lookup
with st.sidebar:
    st.header("Cari barang")
    opts = _item_options(queries.data_fingerprint())
    if not opts.empty:
        idx = int(opts.index[opts["id"] == item_id][0]) if item_id in set(opts["id"]) else 0
        pick = st.selectbox("Barang", opts["label"], index=idx)
        item_id = opts.loc[opts["label"] == pick, "id"].iloc[0]

if not item_id:
    st.info("Pilih barang di sidebar, atau klik satu baris di halaman Inventory / Procurement.")
    st.page_link("pages/inventory.py", label="← Ke Inventory", icon="📋")
    st.stop()

d = queries.item_detail(item_id)
m, c = d["master"], d["calc"]
if not m:
    st.error("Item tidak ditemukan.")
    st.stop()

back = st.session_state.get("detail_origin", "pages/inventory.py")
st.page_link(back, label="← Kembali", icon="↩️")
st.markdown(f"### {m['deskripsi']}")
st.markdown(
    f"`{m['kode_barang'] or '(tanpa kode)'}` · {m['kategori_induk'] or '-'} "
    f"› {m['kategori_anak_1'] or '-'} · UoM **{m['uom'] or '-'}**"
    + (f" · {status_badge(c['stock_status'])}" if c else ""),
    unsafe_allow_html=True,
)
if m["dq_flags"]:
    st.warning(f"Flag data: `{m['dq_flags']}`")
lineage(m["source_file"], m["source_sheet"], m["source_row"])

st.divider()
s1, s2, s3, s4 = st.columns(4)
if c:
    s1.metric("Sisa Stok", "belum terdata" if not c["sisa_stok_known"] else fmt_num(c["sisa_stok"]))
    s2.metric("Safety Stock", "—" if not c["safety_stock_known"] else fmt_num(c["safety_stock"]),
              help="Sumber: sheet SAFETY STOCK" if c["safety_stock_known"] else "Belum ada di sheet SAFETY STOCK")
    s3.metric("Defisit", fmt_num(c["defisit"]))
    s4.metric("Priority", c["priority_level"])
    b1, b2, b3 = st.columns(3)
    b1.metric("Incoming (PPB blm diterima)", fmt_num(c["incoming_qty"]))
    b2.metric("Projected Stock", fmt_num(c["projected_stock"]), help="Sisa + Incoming")
    b3.metric("Rata-rata pakai / bulan", fmt_num(c["avg_monthly_usage"]))
    st.info(f"**Rekomendasi:** {c['rekomendasi']}")

tabs = st.tabs(["🚚 Procurement", "📉 Usage (NPBG)", "📍 Tracking", "🖼️ Blueprint / Lokasi"])

with tabs[0]:
    st.markdown("**PPB**")
    st.dataframe(nice(d["ppb"]), width='stretch', hide_index=True) if not d["ppb"].empty else st.caption("Tidak ada PPB terhubung.")
    st.markdown("**RI (penerimaan)**")
    st.dataframe(nice(d["ri"]), width='stretch', hide_index=True) if not d["ri"].empty else st.caption("Tidak ada RI terhubung.")

with tabs[1]:
    um = d["usage_monthly"]
    if not um.empty:
        st.plotly_chart(px.bar(um, x="ym", y="qty", title="Pemakaian per bulan").update_layout(
            height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_title="", yaxis_title="Qty"),
            width='stretch')
        st.metric("Total keluar (NPBG)", fmt_num(d["npbg"]["qty"].sum()))
    st.dataframe(nice(d["npbg"]), width='stretch', hide_index=True) if not d["npbg"].empty else st.caption("Belum ada NPBG terhubung ke barang ini.")

with tabs[2]:
    for label, key in [("Borrow & Lend", "borrow_lend"), ("STPP", "stpp"), ("Manufaktur & Assembly", "manufacturing")]:
        st.markdown(f"**{label}**")
        st.dataframe(nice(d[key]), width='stretch', hide_index=True) if not d[key].empty else st.caption("—")

with tabs[3]:
    st.write({"Letak Gudang": m["letak_gudang"], "Letak Rak": m["letak_rak"], "Perlu Blueprint?": m["perlu_blueprint"]})
    for ref in ("blueprint_img_ref", "blueprint_pdf_ref", "blueprint_3d_ref"):
        if m[ref]:
            st.markdown(f"- `{ref}`: `{m[ref]}` (referensi file — bukan URL)")
    if not any(m[r] for r in ("blueprint_img_ref", "blueprint_pdf_ref", "blueprint_3d_ref")):
        st.caption("Tidak ada referensi blueprint.")
