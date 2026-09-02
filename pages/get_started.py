"""Mulai — panduan setup. Menonjolkan SATU langkah berikutnya, sisanya ringkas."""
import streamlit as st

from stockwise.ui import fmt_num, page_header, setup_status

page_header("Mulai", "Ikuti langkah yang disorot. Setelah selesai, halaman ini hilang otomatis.", icon="🚀")

s = setup_status()

STEPS = [
    ("Upload Master Inventory", "Upload `DATA.xlsx` — isi katalog barang + parameter safety stock.",
     "pages/data_management.py", "Buka Kelola Data → Upload", s["has_master"]),
    ("Upload data transaksi", "Upload 8 workbook lainnya (PPB-RI, NPBG, Tracking…). Bisa sekaligus, bisa dicicil.",
     "pages/data_management.py", "Buka Kelola Data → Upload", s["has_tx"]),
    ("Cocokkan barang", f"{fmt_num(s['match_open'])} barang transaksi belum pasti terhubung ke master. "
     "Pakai 'Terima massal' untuk yang jelas, review sisanya. Bisa dicicil.",
     "pages/matching_review.py", "Buka Cocokkan Barang", s["match_open"] == 0),
    ("Beresi Safety Stock", f"{fmt_num(s['ss_open'])} barang punya nilai SS/Lead Time beda antar sheet. "
     "Pilih sheet yang benar. Bisa dicicil — barang itu 'belum bisa dinilai' sampai diputuskan.",
     "pages/safety_stock_review.py", "Buka Safety Stock", s["ss_open"] == 0),
]

done_count = sum(d for *_, d in STEPS)
st.progress(done_count / len(STEPS), text=f"{done_count} dari {len(STEPS)} langkah beres")
st.write("")

next_idx = next((i for i, (*_, d) in enumerate(STEPS) if not d), None)

for i, (title, body, page, label, done) in enumerate(STEPS):
    if done:
        st.markdown(f"✅ ~~**{i + 1}. {title}**~~")
    elif i == next_idx:
        with st.container(border=True):
            st.markdown(f"### 👉 {i + 1}. {title}")
            st.markdown(body)
            st.page_link(page, label=label, icon="➡️")
    else:
        st.markdown(f"⬜ **{i + 1}. {title}** — {body.split('.')[0]}.")

st.divider()
if next_idx is None:
    st.success("Semua langkah beres. Sistem siap.")
    st.page_link("pages/executive.py", label="Buka Dashboard", icon="📊")
else:
    st.caption(
        "Tidak punya file dan mau lihat dulu pakai data contoh? Di terminal jalankan "
        "`node --experimental-sqlite tools/build_stockwise_db.mjs` (mengisi dari folder `DATAFIX/`)."
    )
