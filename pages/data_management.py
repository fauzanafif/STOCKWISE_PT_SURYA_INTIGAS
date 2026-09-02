"""Kelola Data — upload semua Excel sekaligus, lihat riwayat & kualitas data."""
import streamlit as st

from stockwise import queries
from stockwise.ingest import ingest_uploads, node_available, rebuild_from_datafix
from stockwise.ui import fmt_num, nice, page_header, recalc_now, setup_status

page_header("Kelola Data", "Upload Excel, pantau proses, dan cek kualitas data.", icon="🗄️")

s = setup_status()
tab_up, tab_hist, tab_dq = st.tabs(["📤 Upload", "🕘 Riwayat", "🔎 Kualitas Data"])

# ─────────────────────────────── Upload ───────────────────────────────
with tab_up:
    st.markdown(
        "**Tarik semua file Excel ke sini sekaligus** (`DATA.xlsx` + 8 file tracking). "
        "Sistem otomatis mengenali tiap file, memproses dengan urutan yang benar (master dulu), "
        "membuang duplikat, mencocokkan barang, dan menghitung ulang — sekali klik."
    )
    ups = st.file_uploader("File Excel (bisa banyak)", type=["xlsx", "xls"],
                           accept_multiple_files=True, key="up_multi")

    if ups:
        st.caption(f"{len(ups)} file siap: " + ", ".join(f"`{u.name}`" for u in ups))
        if st.button("Proses semua", type="primary", width="stretch"):
            if not node_available():
                st.error("Node.js tidak terdeteksi. Install Node 22+ lalu ulangi, "
                         "atau jalankan `node --experimental-sqlite tools/ingest_batch.mjs --dir <folder>` di terminal.")
            else:
                with st.spinner("Membaca, mencocokkan, menghitung… (bisa 1–2 menit)"):
                    res = ingest_uploads(ups)
                if res.get("ok"):
                    sm = res.get("summary", {})
                    st.success(f"Selesai dalam {res.get('seconds', '?')} detik.")
                    m = st.columns(4)
                    m[0].metric("Baris baru", fmt_num(sm.get("inserted")))
                    m[1].metric("Duplikat (dilewati)", fmt_num(sm.get("duplicate")))
                    m[2].metric("Perlu dicocokkan", fmt_num(sm.get("need_review")))
                    m[3].metric("Konflik Safety Stock", fmt_num(sm.get("ss_conflicts")))
                    st.dataframe(nice(queries.read_df(
                        "SELECT module, filename, total_rows, inserted, duplicate FROM upload_batches "
                        "ORDER BY id DESC LIMIT ?", (len(res.get("files", [])) + 4,))),
                        width="stretch", hide_index=True)
                    if res.get("unknown"):
                        st.warning("File tidak dikenali (dilewati): " + ", ".join(res["unknown"]))
                    st.session_state["calc_dirty"] = False
                    st.cache_data.clear()
                    if sm.get("need_review") or sm.get("ss_conflicts"):
                        st.info("Langkah berikutnya: beresi **Matching** dan **Safety Stock** (lihat menu sebelah).")
                else:
                    st.error("Gagal memproses.")
                    st.code(res.get("stderr") or res.get("stdout") or "no output")

    st.divider()
    with st.expander("Alat lain"):
        if st.button("↻ Hitung ulang (tanpa upload)"):
            with st.spinner("Menghitung ulang…"):
                r = recalc_now("manual")
            st.success(f"Selesai — calc run #{r['run_id']}.")
        st.caption("")
        st.markdown("**Rebuild penuh dari folder `DATAFIX/`** — hapus & isi ulang `stockwise.db`. "
                    "Semua keputusan review manual hilang. Untuk bootstrap awal / reset saja.")
        if st.button("Rebuild dari DATAFIX/"):
            with st.spinner("Membangun ulang…"):
                res = rebuild_from_datafix()
            (st.success("Selesai.") if res.get("ok") else st.error("Gagal."))
            st.cache_data.clear()
            st.code((res.get("stdout") or "")[-2500:])

# ─────────────────────────────── Riwayat ───────────────────────────────
with tab_hist:
    df = queries.upload_history()
    if df.empty:
        st.info("Belum ada upload.")
    else:
        st.dataframe(nice(df), width="stretch", hide_index=True)

# ─────────────────────────────── Kualitas ───────────────────────────────
with tab_dq:
    dq = queries.data_quality()
    c = st.columns(4)
    c[0].metric("Item tanpa Safety Stock", fmt_num(dq["no_ss"]))
    c[1].metric("Item tanpa Sisa Stok", fmt_num(dq["no_stock"]))
    c[2].metric("Perlu dicocokkan", fmt_num(s["match_open"]))
    c[3].metric("Konflik Safety Stock", fmt_num(s["ss_open"]))

    cc = st.columns(2)
    cc[0].page_link("pages/matching_review.py", label="→ Cocokkan barang", icon="🤝")
    cc[1].page_link("pages/safety_stock_review.py", label="→ Beresi Safety Stock", icon="🛡️")

    st.markdown("#### Barang transaksi belum ter-match")
    st.dataframe(nice(dq["unmatched"]), width="stretch", hide_index=True)
    st.markdown("#### Flag data master")
    st.dataframe(nice(dq["master_flags"]), width="stretch", hide_index=True)
    st.markdown("#### Peringatan saat import")
    st.dataframe(nice(dq["import_errors"]), width="stretch", hide_index=True)
