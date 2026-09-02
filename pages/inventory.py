"""Inventory — the full item list with stock status, filters, and drill-in."""
import plotly.express as px
import streamlit as st

from stockwise import queries
from stockwise.config import STATUS_COLORS, STATUS_LABELS
from stockwise.ui import fmt_num, page_header, require_db

page_header("Inventory", "Sisa stok tiap barang, status, defisit, dan prioritas. Klik baris untuk detail 360°.", icon="📋")
if not require_db():
    st.stop()


@st.cache_data(show_spinner=False)
def _opts(fp):
    return queries.filter_options()


@st.cache_data(show_spinner=False)
def _table(fp, status, kategori, gudang, search, only_critical):
    return queries.inventory_table(status or None, kategori or None, gudang or None, search or None, only_critical)


fp = queries.data_fingerprint()
opts = _opts(fp)

with st.sidebar:
    st.header("Filter")
    view = st.radio("Tampilan cepat", ["Semua", "Tidak Aman", "Stok Habis", "Critical", "Belum ada SS", "Stok belum terdata"], index=0)
    kategori = st.multiselect("Kategori Induk", opts["kategori"])
    gudang = st.multiselect("Letak Gudang", opts["gudang"])
    search = st.text_input("Cari kode / deskripsi")

status_map = {
    "Semua": [], "Tidak Aman": ["TIDAK_AMAN"], "Stok Habis": ["OUT_OF_STOCK"],
    "Belum ada SS": ["NO_SAFETY_STOCK"], "Stok belum terdata": ["UNKNOWN"],
}
only_critical = view == "Critical"
status = status_map.get(view, [])

df = _table(fp, status, kategori, gudang, search, only_critical)

st.caption(f"Menampilkan **{len(df):,}** item.")
if df.empty:
    st.info("Tidak ada item yang cocok dengan filter.")
    st.stop()

if len(df) > 1 and df["kategori_induk"].notna().any():
    by_cat = (df.assign(n=1).groupby(["kategori_induk", "stock_status"], dropna=True)["n"].sum().reset_index())
    by_cat["Status"] = by_cat["stock_status"].map(lambda s: STATUS_LABELS.get(s, s))
    fig = px.bar(by_cat, x="n", y="kategori_induk", color="Status", orientation="h",
                 color_discrete_map={STATUS_LABELS[k]: v for k, v in STATUS_COLORS.items()})
    fig.update_layout(height=max(220, 26 * by_cat["kategori_induk"].nunique()),
                      margin=dict(l=6, r=6, t=6, b=6), barmode="stack",
                      xaxis_title="Item", yaxis_title="", legend_title="",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    with st.expander("Grafik per kategori", expanded=False):
        st.plotly_chart(fig, use_container_width=True)

view_df = df.copy()
view_df["stock_status"] = view_df["stock_status"].map(lambda s: STATUS_LABELS.get(s, s))
view_df["Sisa"] = df.apply(lambda r: "belum terdata" if not r["sisa_stok_known"] else fmt_num(r["sisa_stok"]), axis=1)
view_df["Safety"] = df.apply(lambda r: "—" if not r["safety_stock_known"] else fmt_num(r["safety_stock"]), axis=1)
cols = {
    "kode_barang": "Kode", "deskripsi": "Deskripsi", "kategori_induk": "Kategori",
    "letak_gudang": "Gudang", "uom": "UoM", "Sisa": "Sisa", "Safety": "Safety",
    "defisit": "Defisit", "stock_status": "Status", "priority_level": "Priority",
    "incoming_qty": "Incoming", "projected_stock": "Projected", "rekomendasi": "Rekomendasi",
}
table = view_df[[c for c in cols if c in view_df.columns]].rename(columns=cols)

event = st.dataframe(
    table, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
)
sel = event.get("selection", {}).get("rows", []) if isinstance(event, dict) else event.selection.rows
if sel:
    item_id = df.iloc[sel[0]]["id"]
    st.session_state["detail_item_id"] = item_id
    st.switch_page("pages/item_detail.py")

st.download_button("⬇️ Download CSV (sesuai filter)", df.to_csv(index=False).encode("utf-8-sig"),
                   file_name="stockwise_inventory.csv", mime="text/csv")
