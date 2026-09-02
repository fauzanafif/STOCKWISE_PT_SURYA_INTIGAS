"""Safety Stock Review — resolve items whose SS / Lead Time differ across the 13
SAFETY STOCK sheets. Pick the authoritative sheet; it updates the calc engine input.
See AUDIT/00_decisions.md [A-1].
"""
import streamlit as st

from stockwise import queries
from stockwise.db import connect
from stockwise.ui import fmt_num, page_header, require_db


def resolve_item(desc_norm: str, sheet: str, values: dict):
    conn = connect()
    try:
        conn.execute(
            """UPDATE safety_stock_params
               SET safety_stock=?, lead_time_days=?, sqrt_lt=?, min_pr=?, avg_12_bln=?,
                   chosen_sheet=?, resolved_by='user', resolved_at=datetime('now'), dq_flag=NULL
               WHERE item_desc_norm=?""",
            (values["safety_stock"], values["lead_time_days"], values["sqrt_lt"],
             values["min_pr"], values["avg_12_bln"], sheet, desc_norm),
        )
        conn.commit()
    finally:
        conn.close()


page_header("Safety Stock Review", "Barang dengan nilai SS / Lead Time berbeda antar sheet SAFETY STOCK. Pilih yang benar.", icon="🛡️")
if not require_db():
    st.stop()

fp = queries.data_fingerprint()
total = queries.scalar("SELECT COUNT(*) FROM safety_stock_params WHERE dq_flag='SS_CONFLICT'")
done = queries.scalar("SELECT COUNT(*) FROM safety_stock_params WHERE chosen_sheet IS NOT NULL")
c1, c2 = st.columns(2)
c1.metric("Konflik belum diputus", f"{total:,}")
c2.metric("Sudah diputus", f"{done:,}")
st.caption("Setelah selesai, jalankan **Hitung ulang** di Data Management agar status & prioritas ikut.")

if total == 0:
    st.success("Tidak ada konflik safety stock. 🎉")
    st.stop()

conflicts = queries.ss_conflicts(limit=400)
PER = 20
n_pages = (len(conflicts) + PER - 1) // PER
pg = st.number_input("Halaman", 1, max(n_pages, 1), 1) - 1
page = conflicts.iloc[pg * PER:(pg + 1) * PER]

for _, row in page.iterrows():
    dn = row["item_desc_norm"]
    with st.container(border=True):
        label = row["deskripsi"] or dn
        st.markdown(f"**{label}**  ·  `{row['kode_barang'] or '—'}`"
                    + (f"  ✅ dipilih: `{row['resolved_sheet']}`" if row["resolved_sheet"] else ""))
        v = queries.ss_variants(dn)
        if v.empty:
            st.caption("Tidak ada varian (aneh — lewati).")
            continue
        vshow = v.rename(columns={
            "source_sheet": "Sheet", "safety_stock": "SS", "lead_time_days": "LT",
            "sqrt_lt": "√LT", "min_pr": "MIN PR", "avg_12_bln": "Avg 12 bln"})
        st.dataframe(vshow, width='stretch', hide_index=True)
        cols = st.columns(min(len(v), 4))
        for i, (_, vr) in enumerate(v.iterrows()):
            btn = cols[i % 4].button(
                f"Pakai {vr['source_sheet']}  (SS {fmt_num(vr['safety_stock'])}, LT {fmt_num(vr['lead_time_days'])})",
                key=f"pick_{dn}_{vr['source_sheet']}")
            if btn:
                resolve_item(dn, vr["source_sheet"], {
                    "safety_stock": vr["safety_stock"], "lead_time_days": vr["lead_time_days"],
                    "sqrt_lt": vr["sqrt_lt"], "min_pr": vr["min_pr"], "avg_12_bln": vr["avg_12_bln"]})
                st.rerun()
