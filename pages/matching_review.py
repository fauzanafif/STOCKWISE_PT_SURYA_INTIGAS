"""Matching Review — approve/reject fuzzy matches. Fuzzy is NEVER auto-applied (RULE 8)."""
import streamlit as st

from stockwise import queries
from stockwise.db import connect
from stockwise.ui import page_header, require_db


def apply_decision(table, row_id, item_id, review_id, decision="ACCEPT"):
    conn = connect()
    try:
        if decision == "ACCEPT":
            conn.execute(f"UPDATE {table} SET master_item_id = ?, match_status = 'MATCHED' WHERE id = ?", (item_id, row_id))
            conn.execute("UPDATE matching_reviews SET decision='ACCEPT', decided_at=datetime('now') WHERE id = ?", (review_id,))
            conn.execute(
                "UPDATE matching_reviews SET decision='REJECT', decided_at=datetime('now') "
                "WHERE source_table=? AND source_row_id=? AND id<>? AND decision='PENDING'",
                (table, row_id, review_id))
        else:
            conn.execute(f"UPDATE {table} SET match_status = 'NEW_ITEM' WHERE id = ?", (row_id,))
            conn.execute(
                "UPDATE matching_reviews SET decision='NEW_ITEM', decided_at=datetime('now') "
                "WHERE source_table=? AND source_row_id=? AND decision='PENDING'", (table, row_id))
        conn.commit()
    finally:
        conn.close()


page_header("Matching Review", "Barang transaksi yang belum pasti terhubung ke master. Keputusan Anda disimpan.", icon="🤝")
if not require_db():
    st.stop()

pending_total = queries.scalar(
    "SELECT COUNT(DISTINCT source_table || source_row_id) FROM matching_reviews WHERE decision='PENDING'")
st.metric("Baris menunggu keputusan", f"{pending_total:,}")
st.caption("Setelah menyelesaikan review, jalankan ulang kalkulasi di Data Management agar angka dashboard ikut.")

q = queries.matching_queue(limit=1500)
if q.empty:
    st.success("Tidak ada yang perlu direview. 🎉")
    st.stop()

all_groups = list(q.groupby(["source_table", "source_row_id", "source_desc"], dropna=False))
PER_PAGE = 25
n_pages = (len(all_groups) + PER_PAGE - 1) // PER_PAGE
c1, c2 = st.columns([3, 1])
c1.caption(f"{len(all_groups)} baris dengan kandidat (confidence tertinggi dulu).")
pg = c2.number_input("Halaman", 1, max(n_pages, 1), 1) - 1
groups = all_groups[pg * PER_PAGE:(pg + 1) * PER_PAGE]

for (table, row_id, src_desc), grp in groups:
    with st.container(border=True):
        st.markdown(f"**{src_desc}**  ·  `{table}` baris #{int(row_id)}")
        for _, cand in grp.iterrows():
            cc = st.columns([5, 1, 2])
            cc[0].markdown(f"↳ {cand['candidate_desc'] or '(tidak ada kandidat)'}")
            cc[1].markdown(f"`{cand['confidence']:.2f}`" if cand["confidence"] else "—")
            if cand["candidate_item_id"] and cc[2].button("Terima ini", key=f"acc_{cand['id']}"):
                apply_decision(table, int(row_id), cand["candidate_item_id"], int(cand["id"]))
                st.rerun()
        b1, b2 = st.columns(2)
        if b1.button("Semua salah — tandai NEW ITEM", key=f"new_{table}_{row_id}"):
            apply_decision(table, int(row_id), None, None, decision="NEW_ITEM")
            st.rerun()
        b2.button("Lewati", key=f"skip_{table}_{row_id}")
