"""Matching Review — link transaction items to master. Fuzzy is NEVER auto-applied (RULE 8).

Workflows:
  • Accept a candidate            -> row.master_item_id set, review ACCEPTed
  • Mark "barang baru" (NEW ITEM)  -> row flagged, optionally create a master_items row
  • Bulk accept all >= threshold   -> for EXACT_* / high-confidence FUZZY
"""
import streamlit as st

from utils import queries
from utils.database import connect
from utils.dashboard_ui import apply_changes_banner, mark_dirty, page_header, recalc_now, require_db

TX_TABLES = {
    "ppb_lines": "deskripsi", "ppb_changes": "deskripsi", "ri_lines": "deskripsi",
    "npbg_lines": "deskripsi", "borrow_lend": "deskripsi", "stpp": "deskripsi",
    "tire_transactions": "deskripsi_ban_baru", "manufacturing": "hasil_produk", "used_returns": "deskripsi",
}


def _accept(conn, table, row_id, item_id, review_id):
    conn.execute(f"UPDATE {table} SET master_item_id=?, match_status='MATCHED' WHERE id=?", (item_id, row_id))
    conn.execute("UPDATE matching_reviews SET decision='ACCEPT', decided_by='user', decided_at=datetime('now') WHERE id=?", (review_id,))
    conn.execute(
        "UPDATE matching_reviews SET decision='REJECT', decided_at=datetime('now') "
        "WHERE source_table=? AND source_row_id=? AND id<>? AND decision='PENDING'", (table, row_id, review_id))


def accept_one(table, row_id, item_id, review_id):
    conn = connect()
    try:
        _accept(conn, table, row_id, item_id, review_id)
        conn.commit()
    finally:
        conn.close()
    mark_dirty()


def bulk_accept(table, min_conf):
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT mr.id, mr.source_table, mr.source_row_id, mr.candidate_item_id
               FROM matching_reviews mr
               WHERE mr.decision='PENDING' AND mr.candidate_item_id IS NOT NULL AND mr.confidence >= ?
               AND (? = '' OR mr.source_table = ?)
               AND mr.id IN (SELECT MIN(id) FROM matching_reviews WHERE decision='PENDING' GROUP BY source_table, source_row_id)
            """, (min_conf, table or "", table or "")).fetchall()
        for r in rows:
            _accept(conn, r["source_table"], r["source_row_id"], r["candidate_item_id"], r["id"])
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def create_master_from(table, row_id, desc):
    conn = connect()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM master_items").fetchone()["c"]
        new_id = f"ITEM-{n + 1:06d}"
        from utils.textnorm import desc_core, desc_norm
        conn.execute(
            """INSERT INTO master_items (id, deskripsi, deskripsi_norm, deskripsi_core, dq_flags, source_file)
               VALUES (?,?,?,?, 'CREATED_FROM_TRANSACTION', ?)""",
            (new_id, desc, desc_norm(desc), desc_core(desc), f"matching_review:{table}"))
        conn.execute(f"UPDATE {table} SET master_item_id=?, match_status='MATCHED' WHERE id=?", (new_id, row_id))
        conn.execute(
            "UPDATE matching_reviews SET decision='NEW_ITEM', decided_by='user', decided_at=datetime('now') "
            "WHERE source_table=? AND source_row_id=? AND decision='PENDING'", (table, row_id))
        conn.commit()
        mark_dirty()
        return new_id
    finally:
        conn.close()


page_header("Matching Review", "Hubungkan barang transaksi ke master. Keputusan Anda disimpan.", icon="🤝")
if not require_db():
    st.stop()
apply_changes_banner()

stats = queries.matching_stats()
c1, c2 = st.columns(2)
c1.metric("Baris dengan kandidat — menunggu", f"{stats['pending']:,}")
c2.metric("Barang belum dikenal (NEW_ITEM)", f"{int(stats['new_items']['n'].sum()):,}")
st.caption("Setiap keputusan langsung disimpan. Tombol **↻ Terapkan** muncul di dashboard untuk hitung ulang.")

with st.sidebar:
    st.header("Filter antrian")
    tbl = st.selectbox("Tabel sumber", ["(semua)"] + stats["tables"])
    tbl = None if tbl == "(semua)" else tbl
    min_conf = st.slider("Confidence minimum", 0.0, 1.0, 0.0, 0.05)
    st.divider()
    st.subheader("Terima massal")
    thr = st.slider("Terima semua kandidat teratas dengan confidence ≥", 0.75, 1.0, 0.98, 0.01)
    if st.button(f"Terima {('semua tabel' if not tbl else tbl)} ≥ {thr:.2f}", type="primary"):
        with st.spinner("Mencocokkan & menghitung ulang…"):
            n = bulk_accept(tbl, thr)
            recalc_now("bulk match")
        st.success(f"{n} baris di-match & dashboard sudah diperbarui.")
        st.rerun()

tab_q, tab_new = st.tabs(["🔗 Antrian kandidat", "🆕 Barang belum dikenal"])

with tab_q:
    q = queries.matching_queue(limit=1500, table=tbl, min_conf=min_conf)
    if q.empty:
        st.success("Tidak ada yang perlu direview pada filter ini.")
    else:
        groups = list(q.groupby(["source_table", "source_row_id", "source_desc"], dropna=False))
        PER = 25
        n_pages = (len(groups) + PER - 1) // PER
        cc1, cc2 = st.columns([3, 1])
        cc1.caption(f"{len(groups)} baris.")
        pg = cc2.number_input("Halaman", 1, max(n_pages, 1), 1) - 1
        for (table, row_id, src_desc), grp in groups[pg * PER:(pg + 1) * PER]:
            with st.container(border=True):
                st.markdown(f"**{src_desc}**  ·  `{table}` #{int(row_id)}")
                for _, cand in grp.iterrows():
                    a, b, c = st.columns([6, 1, 2])
                    a.markdown(f"↳ {cand['candidate_desc']}")
                    b.markdown(f"`{cand['confidence']:.2f}`")
                    if c.button("Terima", key=f"acc_{cand['id']}"):
                        accept_one(table, int(row_id), cand["candidate_item_id"], int(cand["id"]))
                        st.rerun()
                if st.button("Semua salah → barang baru", key=f"new_{table}_{row_id}"):
                    nid = create_master_from(table, int(row_id), src_desc)
                    st.success(f"Dibuat {nid}")
                    st.rerun()

with tab_new:
    st.caption("Barang di transaksi yang tidak punya kandidat sama sekali. Buat master item untuk yang valid.")
    st.dataframe(stats["new_items"].rename(columns={"t": "Tabel", "n": "Jumlah baris"}),
                 width='stretch', hide_index=True)
    tsel = st.selectbox("Lihat daftar dari tabel", list(TX_TABLES))
    col = TX_TABLES[tsel]
    df = queries.read_df(
        f"SELECT id, {col} AS deskripsi, COUNT(*) OVER (PARTITION BY {col}) AS n_baris "
        f"FROM {tsel} WHERE match_status='NEW_ITEM' AND {col} IS NOT NULL "
        f"GROUP BY {col} ORDER BY n_baris DESC LIMIT 300")
    if df.empty:
        st.info("Tidak ada.")
    else:
        st.dataframe(df[["deskripsi", "n_baris"]], width='stretch', hide_index=True)
        pick = st.selectbox("Buat master item dari", df["deskripsi"])
        if st.button("Buat master item"):
            rid = int(df.loc[df["deskripsi"] == pick, "id"].iloc[0])
            nid = create_master_from(tsel, rid, pick)
            st.success(f"Dibuat {nid}. Baris lain dengan deskripsi sama ikut ter-match saat berikutnya diproses/dihitung ulang.")
