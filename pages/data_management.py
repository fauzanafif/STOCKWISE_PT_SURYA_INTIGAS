"""Data Management — Upload Center, processing history, data quality."""
import streamlit as st

from stockwise import queries
from stockwise.config import MODULES
from stockwise.ingest import ingest_upload, node_available, rebuild_from_datafix
from stockwise.ui import fmt_num, page_header

page_header("Data Management", "Upload Excel per modul, riwayat proses, dan kualitas data.", icon="🗄️")

tab_up, tab_hist, tab_dq = st.tabs(["📤 Upload Center", "🕘 Riwayat Proses", "🔎 Data Quality"])

with tab_up:
    st.markdown(
        "Pilih modul, upload file Excel-nya (file kumulatif penuh — sistem membuang duplikat lewat UPSERT). "
        "**Upload `DATA.xlsx` (Master) dulu** supaya barang di file lain bisa dicocokkan."
    )
    module = st.selectbox(
        "Modul", list(MODULES), format_func=lambda k: f"{MODULES[k]['label']}  —  {MODULES[k]['file_hint']}")
    st.caption("Sheet yang dibaca: " + ", ".join(f"`{s}`" for s in MODULES[module]["sheets"]))
    up = st.file_uploader("File Excel", type=["xlsx", "xls"], key=f"up_{module}")

    if up is not None and st.button("Proses & Import", type="primary"):
        if not node_available():
            st.error("Node.js tidak terdeteksi. Jalankan lewat terminal:\n\n"
                     "`node --experimental-sqlite tools/ingest_one.mjs " + module + " <path-file>`")
        else:
            with st.spinner("Membaca, mencocokkan, dan menyimpan…"):
                res = ingest_upload(module, up)
            if res.get("ok"):
                st.success("Selesai.")
                s = res.get("summary", res)
                cols = st.columns(5)
                cols[0].metric("Total baris", fmt_num(s.get("total")))
                cols[1].metric("Insert", fmt_num(s.get("inserted")))
                cols[2].metric("Duplikat (skip)", fmt_num(s.get("duplicate")))
                cols[3].metric("Perlu review", fmt_num(s.get("need_review")))
                cols[4].metric("Matched", fmt_num(s.get("matched")))
                if s.get("errors"):
                    st.warning(f"{len(s['errors'])} peringatan — lihat tab Data Quality.")
            else:
                st.error("Gagal.")
                st.code(res.get("stderr") or res.get("stdout") or "no output")

    st.divider()
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("♻️ Hitung ulang (setelah Matching Review)"):
            from stockwise.calc import run_calc
            with st.spinner("Menghitung ulang status & prioritas…"):
                r = run_calc(notes="manual recalculate")
            st.success(f"Selesai — calc run #{r['run_id']}, {r['items']:,} item.")

    with st.expander("Rebuild penuh dari folder DATAFIX/ (hapus & isi ulang stockwise.db)"):
        st.caption("Dipakai untuk bootstrap awal atau reset. Semua keputusan matching manual akan hilang.")
        if st.button("Rebuild sekarang"):
            with st.spinner("Membangun ulang… (bisa beberapa menit)"):
                res = rebuild_from_datafix()
            st.success("Selesai.") if res.get("ok") else st.error("Gagal.")
            st.code((res.get("stdout") or "")[-3000:])

with tab_hist:
    df = queries.upload_history()
    if df.empty:
        st.info("Belum ada batch upload.")
    else:
        st.dataframe(df, width='stretch', hide_index=True)

with tab_dq:
    dq = queries.data_quality()
    c = st.columns(3)
    c[0].metric("Item tanpa Safety Stock", fmt_num(dq["no_ss"]))
    c[1].metric("Item tanpa Sisa Stok", fmt_num(dq["no_stock"]))
    pend = queries.scalar("SELECT COUNT(DISTINCT source_table || source_row_id) FROM matching_reviews WHERE decision='PENDING'")
    c[2].metric("Baris transaksi perlu match", fmt_num(pend))
    st.page_link("pages/matching_review.py", label="→ Buka Matching Review", icon="🤝")

    st.markdown("#### Barang transaksi belum ter-match")
    st.dataframe(dq["unmatched"], width='stretch', hide_index=True)
    st.markdown("#### Flag data master")
    st.dataframe(dq["master_flags"], width='stretch', hide_index=True)
    st.markdown("#### Peringatan import")
    st.dataframe(dq["import_errors"], width='stretch', hide_index=True)
