"""Master Data — the item catalogue, aliases, and safety-stock parameters."""
import streamlit as st

from stockwise import queries
from stockwise.db import read_df
from stockwise.ui import fmt_num, page_header, require_db

page_header("Master Data", "Katalog barang, alias, dan parameter safety stock (dari 13 sheet SAFETY STOCK).", icon="🗂️")
if not require_db():
    st.stop()

t1, t2, t3 = st.tabs(["Katalog Barang", "Safety Stock Params", "Alias"])

with t1:
    c = st.columns(4)
    c[0].metric("Total item", fmt_num(queries.scalar("SELECT COUNT(*) FROM master_items")))
    c[1].metric("Punya Kode Barang", fmt_num(queries.scalar("SELECT COUNT(*) FROM master_items WHERE kode_barang IS NOT NULL")))
    c[2].metric("Kode duplikat / kosong", fmt_num(queries.scalar("SELECT COUNT(*) FROM master_items WHERE dq_flags LIKE '%KODE%'")))
    c[3].metric("Kategori Induk", fmt_num(queries.scalar("SELECT COUNT(DISTINCT kategori_induk) FROM master_items")))
    search = st.text_input("Cari")
    sql = ("SELECT kode_barang, deskripsi, kategori_induk, kategori_anak_1, uom, letak_gudang, letak_rak, "
           "perlu_blueprint, dq_flags FROM master_items")
    if search:
        sql += " WHERE deskripsi LIKE :q OR kode_barang LIKE :q"
        df = read_df(sql + " ORDER BY deskripsi LIMIT 3000", {"q": f"%{search}%"})
    else:
        df = read_df(sql + " ORDER BY deskripsi LIMIT 3000")
    st.dataframe(df, width='stretch', hide_index=True)
    st.caption(f"{len(df):,} baris ditampilkan (maks 3000).")

with t2:
    st.caption("Diambil apa adanya dari sheet SAFETY STOCK (A-1). Rumus internal belum direkayasa ulang.")
    df = read_df(
        "SELECT item_description, master_item_id, lead_time_days, sqrt_lt, safety_stock, min_pr, "
        "avg_1_bln, avg_3_bln, avg_6_bln, avg_12_bln, source_sheet, dq_flag FROM safety_stock_params ORDER BY safety_stock DESC")
    c = st.columns(3)
    c[0].metric("Baris parameter", fmt_num(len(df)))
    c[1].metric("SS > 0", fmt_num((df["safety_stock"].fillna(0) > 0).sum()))
    c[2].metric("Konflik antar-sheet", fmt_num((df["dq_flag"] == "SS_CONFLICT").sum()))
    st.dataframe(df, width='stretch', hide_index=True)

with t3:
    df = read_df("SELECT master_item_id, alias, source FROM item_aliases")
    if df.empty:
        st.info("Belum ada alias. Kolom `Nama Alias` di master hanya berisi 'Ya'/'Tidak' (bukan alias) — lihat [A-6].")
    else:
        st.dataframe(df, width='stretch', hide_index=True)
