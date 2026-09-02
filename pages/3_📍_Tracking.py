"""Tracking — Borrow/Lend, STPP, Ban Luar, Maintenance Kendaraan, Manufaktur & Assembly, Pengembalian Bekas."""
import streamlit as st

from utils import queries
from utils.database import read_df
from utils.dashboard_ui import fmt_num, nice, page_header, require_db

page_header("Tracking", "Modul operasional: pinjam-pakai, STPP, ban, maintenance kendaraan, manufaktur, pengembalian bekas.", icon="📍")
if not require_db():
    st.stop()


def show(sql, note=None, search_cols=None):
    df = read_df(sql)
    if search_cols:
        q = st.text_input("Cari", key="s" + str(hash(sql)))
        if q:
            mask = False
            for c in search_cols:
                mask = mask | df[c].astype(str).str.contains(q, case=False, na=False)
            df = df[mask]
    st.caption(f"{len(df):,} baris." + (f" {note}" if note else ""))
    st.dataframe(nice(df), width='stretch', hide_index=True)


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
    show("SELECT arah, tgl_pinjam, deskripsi, qty, satuan_raw, pihak, keperluan, est_hari, "
         "status, ref_keluar, ref_kembali, tgl_kembali, match_status FROM borrow_lend ORDER BY tgl_pinjam DESC",
         search_cols=["deskripsi", "pihak"])

with t2:
    show("SELECT no_seri, deskripsi, qty, peminta, penempatan, status, tgl_npbg, ref_npbg, "
         "tgl_ri, ref_kembali, match_status FROM stpp ORDER BY tgl_npbg DESC",
         search_cols=["deskripsi", "no_seri", "peminta"])

with t3:
    st.markdown("**Ban Luar** — pergantian ban per kendaraan")
    show("SELECT nopol, tgl_npbg, ref_npbg, deskripsi_ban_baru, no_seri_baru, ban_pos, status, "
         "tgl_ri, ref_ri, deskripsi_ban_lama, no_seri_lama FROM tire_transactions ORDER BY tgl_npbg DESC",
         search_cols=["nopol", "deskripsi_ban_baru", "no_seri_baru"])
    with st.expander("Ban Luar BPN (snapshot cabang Balikpapan)"):
        st.dataframe(nice(read_df("SELECT seq_no, tanggal_cut_off, nopol, deskripsi_ban, no_seri, keterangan FROM tire_bpn_snapshots")),
                     width='stretch', hide_index=True)
    with st.expander("Deliver & Receive Ban SIG-BPN"):
        st.dataframe(nice(read_df("SELECT nopol, tgl_npbg, ref_npbg, deskripsi_out, no_seri_out, tgl_ri, ref_ri, deskripsi_in, no_seri_in FROM tire_deliver_receive")),
                     width='stretch', hide_index=True)

with t4:
    show("SELECT no_spk, sub_spk, nopol, tgl_laporan, keterangan_awal, bengkel, status, "
         "ref_npbg, tgl_selesai FROM asset_maintenance ORDER BY tgl_laporan DESC",
         search_cols=["no_spk", "nopol"])

with t5:
    show("SELECT jenis, no_dok, sub, hasil_produk, no_seri, proses, status, ref_npbg, ref_ri, "
         "tgl, tgl_selesai, match_status FROM manufacturing ORDER BY tgl DESC",
         search_cols=["no_dok", "hasil_produk", "no_seri"])

with t6:
    st.caption("Nilai qty negatif = shortage barang bekas (dipertahankan apa adanya).")
    show("SELECT format, ref_npbg, ref_ri, part_type, deskripsi, qty, status, keterangan FROM used_returns ORDER BY id DESC",
         search_cols=["deskripsi", "part_type", "ref_npbg"])
