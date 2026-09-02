"""Tracking — Borrow/Lend, STPP, Ban Luar, Maintenance Kendaraan, Manufaktur & Assembly, Pengembalian Bekas."""
import streamlit as st

from stockwise import queries
from stockwise.db import read_df
from stockwise.ui import fmt_num, page_header, require_db

page_header("Tracking", "Modul operasional: pinjam-pakai, STPP, ban, maintenance kendaraan, manufaktur, pengembalian bekas.", icon="📍")
if not require_db():
    st.stop()

fp = queries.data_fingerprint()
tc = queries.tracking_counts()
cols = st.columns(5)
cols[0].metric("Borrow/Lend aktif", fmt_num(tc["borrow_lend_active"]))
cols[1].metric("STPP ACTIVE", fmt_num(tc["stpp_active"]))
cols[2].metric("Maintenance open", fmt_num(tc["maint_open"]))
cols[3].metric("Manufaktur open", fmt_num(tc["mfg_open"]))
cols[4].metric("Transaksi ban", fmt_num(tc["tire_total"]))

t1, t2, t3, t4, t5, t6 = st.tabs(
    ["Borrow & Lend", "STPP", "Ban Luar", "Maintenance Kendaraan", "Manufaktur & Assembly", "Pengembalian Bekas"])

with t1:
    st.dataframe(read_df(
        "SELECT arah, tgl_pinjam, deskripsi, qty, satuan_raw, pihak, keperluan, est_hari, "
        "status, ref_keluar, ref_kembali, tgl_kembali, match_status FROM borrow_lend ORDER BY tgl_pinjam DESC"),
        use_container_width=True, hide_index=True)

with t2:
    st.dataframe(read_df(
        "SELECT no_seri, deskripsi, qty, peminta, penempatan, status, tgl_npbg, ref_npbg, "
        "tgl_ri, ref_kembali, match_status FROM stpp ORDER BY tgl_npbg DESC"),
        use_container_width=True, hide_index=True)

with t3:
    st.markdown("**Ban Luar** — pergantian ban per kendaraan")
    st.dataframe(read_df(
        "SELECT nopol, tgl_npbg, ref_npbg, deskripsi_ban_baru, no_seri_baru, ban_pos, status, "
        "tgl_ri, ref_ri, deskripsi_ban_lama, no_seri_lama FROM tire_transactions ORDER BY tgl_npbg DESC"),
        use_container_width=True, hide_index=True)
    with st.expander("Ban Luar BPN (snapshot cabang Balikpapan)"):
        st.dataframe(read_df("SELECT * FROM tire_bpn_snapshots"), use_container_width=True, hide_index=True)
    with st.expander("Deliver & Receive Ban SIG-BPN"):
        st.dataframe(read_df("SELECT * FROM tire_deliver_receive"), use_container_width=True, hide_index=True)

with t4:
    st.dataframe(read_df(
        "SELECT no_spk, sub_spk, nopol, tgl_laporan, keterangan_awal, bengkel, status, "
        "ref_npbg, tgl_selesai FROM asset_maintenance ORDER BY tgl_laporan DESC"),
        use_container_width=True, hide_index=True)

with t5:
    st.dataframe(read_df(
        "SELECT jenis, no_dok, sub, hasil_produk, no_seri, proses, status, ref_npbg, ref_ri, "
        "tgl, tgl_selesai, match_status FROM manufacturing ORDER BY tgl DESC"),
        use_container_width=True, hide_index=True)

with t6:
    st.markdown("**Long** (per barang) — nilai qty negatif = shortage bekas")
    st.dataframe(read_df(
        "SELECT format, ref_npbg, ref_ri, part_type, deskripsi, qty, status, keterangan FROM used_returns ORDER BY id DESC"),
        use_container_width=True, hide_index=True)
