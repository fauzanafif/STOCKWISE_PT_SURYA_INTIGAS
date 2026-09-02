"""Procurement — priority buy list + PPB→PO→RI status tracker."""
import streamlit as st

from utils import queries
from utils.dashboard_ui import apply_changes_banner, fmt_num, page_header, require_db

page_header("Procurement", "Barang yang perlu dibeli, diurutkan mendesak — plus status PPB / PO / RI.", icon="🚚")
if not require_db():
    st.stop()
apply_changes_banner()

fp = queries.data_fingerprint()
tab1, tab2 = st.tabs(["🎯 Priority Buy List", "📋 Status PPB → PO → RI"])

with tab1:
    prio = queries.procurement_priority()
    if prio.empty:
        st.success("Tidak ada barang berstatus Tidak Aman / Stok Habis pada data yang lengkap.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Barang perlu aksi", f"{len(prio):,}")
        c2.metric("Total defisit", fmt_num(prio["defisit"].sum()))
        c3.metric("Priority HIGH", f"{(prio['priority_level'] == 'HIGH').sum():,}")
        show = prio[["kode_barang", "deskripsi", "letak_gudang", "sisa_stok", "safety_stock",
                     "defisit", "lead_time_days", "incoming_qty", "projected_stock",
                     "priority_score", "priority_level", "rekomendasi"]].copy()
        show.columns = ["Kode", "Deskripsi", "Gudang", "Sisa", "Safety", "Defisit", "Lead Time",
                        "Incoming", "Projected", "Score", "Priority", "Rekomendasi"]
        ev = st.dataframe(show, width='stretch', hide_index=True, on_select="rerun",
                          selection_mode="single-row",
                          column_config={"Score": st.column_config.NumberColumn(format="%.1f")})
        rows = ev["selection"]["rows"] if isinstance(ev, dict) else ev.selection.rows
        if rows:
            st.session_state["detail_item_id"] = prio.iloc[rows[0]]["id"]
            st.session_state["detail_origin"] = "pages/1_🚚_Procurement.py"
            st.switch_page("pages/4_🔎_Detail_Barang.py")
        st.caption("Klik baris → detail 360°. Incoming = qty PPB belum-final − RI yang sudah masuk (perkiraan, [A-17]).")
        st.download_button("⬇️ CSV", show.to_csv(index=False).encode("utf-8-sig"),
                           "procurement_priority.csv", "text/csv")

with tab2:
    df = queries.ppb_ri_status()
    if df.empty:
        st.info("Belum ada data PPB.")
    else:
        df["outstanding"] = (df["qty_ppb"].fillna(0) - df["qty_ri"].fillna(0)).clip(lower=0)
        f = st.text_input("Cari No PPB / vendor")
        if f:
            df = df[df["no_ppb"].str.contains(f, case=False, na=False) | df["vendor"].fillna("").str.contains(f, case=False, na=False)]
        show = df[["no_ppb", "tgl_ppb", "status", "n_item", "qty_ppb", "qty_ri", "outstanding", "n_po", "vendor"]].copy()
        show.columns = ["No PPB", "Tgl", "Status", "Item", "Qty PPB", "Qty RI", "Outstanding", "# PO", "Vendor"]
        st.dataframe(show, width='stretch', hide_index=True)
        st.caption(f"{len(df):,} PPB. Outstanding = Qty PPB − Qty RI (per nomor PPB).")
