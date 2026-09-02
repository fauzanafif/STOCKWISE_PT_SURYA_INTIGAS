"""Get Started — the one-time setup checklist. Auto-shown until the system is ready."""
import streamlit as st

from stockwise.ui import fmt_num, page_header, setup_status

page_header("Get Started", "Langkah menyiapkan STOCKWISE. Ikuti dari atas ke bawah.", icon="🚀")

s = setup_status()

if s["ready"] and s["ss_open"] == 0 and s["match_open"] == 0:
    st.success("Semua langkah selesai — sistem siap dipakai.")
    st.page_link("pages/executive.py", label="Buka Executive Dashboard", icon="📦")
    st.stop()

st.progress(s["stage"] / 5, text=f"Langkah selesai: {s['stage']} / 5")
st.write("")


def step(done: bool, title: str, body: str, link=None, link_label=None, warn=False):
    icon = "✅" if done else ("⚠️" if warn else "⬜")
    with st.container(border=True):
        st.markdown(f"### {icon}  {title}")
        st.markdown(body)
        if link and not done:
            st.page_link(link, label=link_label or "Buka", icon="➡️")


step(
    s["has_master"], "1 · Upload Master Inventory",
    "Upload `DATA.xlsx` di **Data Management → Upload Center**, modul *Master Inventory*. "
    "Ini isi katalog barang + parameter safety stock dari 13 sheet `SAFETY STOCK *`."
    + ("" if not s["has_master"] else "  \nMaster sudah masuk."),
    "pages/data_management.py", "Data Management",
)
step(
    s["has_tx"], "2 · Upload data transaksi",
    "Upload sisa 8 workbook (PPB-RI, NPBG, Tracking …), satu per modul. File kumulatif penuh — "
    "duplikat dibuang otomatis. Bisa dicicil."
    + ("" if not s["has_tx"] else "  \nData transaksi sudah ada."),
    "pages/data_management.py", "Data Management",
)
step(
    s["ss_open"] == 0, "3 · Beresi konflik Safety Stock",
    f"**{fmt_num(s['ss_open'])}** barang punya nilai Safety Stock / Lead Time berbeda antar sheet. "
    "Pilih sheet yang benar per barang. (Bisa dilewati dulu — barang itu statusnya "
    "*belum bisa dinilai* sampai diputuskan.)",
    "pages/safety_stock_review.py", "Safety Stock Review", warn=s["ss_open"] > 0,
)
step(
    s["match_open"] == 0, "4 · Beresi Matching",
    f"**{fmt_num(s['match_open'])}** barang transaksi belum pasti terhubung ke master. "
    "Pakai *Terima massal* untuk yang confidence tinggi, review sisanya. (Bisa dicicil.)",
    "pages/matching_review.py", "Matching Review", warn=s["match_open"] > 0,
)
step(
    s["calc_done"], "5 · Hitung ulang",
    "Setelah upload / review, tekan **♻️ Hitung ulang** di Data Management supaya status, defisit, "
    "prioritas, dan projected stock ter-update.",
    "pages/data_management.py", "Data Management",
)

st.divider()
st.caption(
    "Belum punya file dan mau lihat dulu dengan data contoh? Jalankan di terminal: "
    "`node --experimental-sqlite tools/build_stockwise_db.mjs` — mengisi dari folder `DATAFIX/`."
)
