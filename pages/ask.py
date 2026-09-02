"""Ask STOCKWISE — quick answers to common management questions, traceable to source.

Rule-based for now (no LLM): recognises a handful of question shapes and runs the
matching query. Every answer links back to the page / rows it came from.
"""
import streamlit as st

from stockwise import queries
from stockwise.db import read_df
from stockwise.ui import fmt_num, page_header, require_db

page_header("Ask STOCKWISE", "Pertanyaan manajemen yang sering muncul — jawaban langsung dari data.", icon="💬")
if not require_db():
    st.stop()

PRESETS = {
    "Barang apa yang stoknya habis?": "out_of_stock",
    "Barang mana yang tidak aman / perlu dibeli?": "unsafe",
    "Barang apa yang paling banyak dipakai?": "top_usage",
    "Divisi mana paling banyak menggunakan barang?": "by_divisi",
    "PPB mana yang belum selesai?": "ppb_open",
    "Berapa total sisa stok & kesehatan inventory?": "overview",
}

choice = st.radio("Pertanyaan", list(PRESETS), index=0)
kind = PRESETS[choice]
st.divider()

if kind == "overview":
    k = queries.executive_kpis()
    st.markdown(
        f"- Total item: **{fmt_num(k['total_item'])}**\n"
        f"- Total sisa stok (item terdata): **{fmt_num(k['total_stok'])}**\n"
        f"- Tidak aman: **{fmt_num(k['tidak_aman'])}** · Stok habis: **{fmt_num(k['out_of_stock'])}** · Critical: **{fmt_num(k['critical'])}**\n"
        f"- Skor kesehatan: **{k['stock_health']}%** (dari {fmt_num(k['ss_known'])} item yang punya Safety Stock)\n"
        f"- Item belum ada Safety Stock: **{fmt_num(k['no_ss'])}** · sisa stok belum terdata: **{fmt_num(k['unknown_stok'])}**"
    )
    st.page_link("pages/executive.py", label="→ Executive Dashboard", icon="📦")

elif kind == "out_of_stock":
    df = queries.inventory_table(status=["OUT_OF_STOCK"])
    st.markdown(f"**{len(df)}** barang stoknya 0 (dan punya safety stock > 0):")
    st.dataframe(df[["kode_barang", "deskripsi", "safety_stock", "lead_time_days", "priority_level"]],
                 use_container_width=True, hide_index=True)
    st.page_link("pages/inventory.py", label="→ Inventory (filter Stok Habis)", icon="📋")

elif kind == "unsafe":
    df = queries.procurement_priority()
    st.markdown(f"**{len(df)}** barang di bawah safety stock, diurutkan prioritas:")
    st.dataframe(df[["kode_barang", "deskripsi", "sisa_stok", "safety_stock", "defisit",
                     "incoming_qty", "projected_stock", "priority_level", "rekomendasi"]].head(100),
                 use_container_width=True, hide_index=True)
    st.page_link("pages/procurement.py", label="→ Procurement", icon="🚚")

elif kind == "top_usage":
    df = queries.usage_summary()["top_items"]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.page_link("pages/usage.py", label="→ Usage Analysis", icon="📉")

elif kind == "by_divisi":
    df = queries.usage_summary()["by_divisi"]
    st.dataframe(df, use_container_width=True, hide_index=True)

elif kind == "ppb_open":
    df = read_df(
        "SELECT no_ppb, MIN(tgl_ppb) tgl, MAX(status) status, COUNT(*) item, SUM(qty) qty_ppb, "
        "(SELECT COALESCE(SUM(qty),0) FROM ri_lines r WHERE r.no_ppb=p.no_ppb) qty_ri "
        "FROM ppb_lines p WHERE LOWER(COALESCE(status,'')) NOT IN ('completed','close','error') "
        "GROUP BY no_ppb ORDER BY tgl DESC")
    st.markdown(f"**{len(df)}** PPB belum selesai:")
    st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("Jawaban dihitung oleh calculation engine dari stockwise.db — bisa ditelusuri ke baris Excel lewat Item Detail.")
