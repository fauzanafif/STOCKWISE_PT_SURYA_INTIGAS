"""Usage Analysis — consumption from NPBG: trend, top items, by division/customer/project."""
import plotly.express as px
import streamlit as st

from stockwise import queries
from stockwise.ui import fmt_num, page_header, require_db

page_header("Usage Analysis", "Pemakaian barang berdasarkan NPBG — apa yang keluar, oleh siapa, untuk apa.", icon="📉")
if not require_db():
    st.stop()


@st.cache_data(show_spinner=False)
def _usage(fp):
    return queries.usage_summary()


u = _usage(queries.data_fingerprint())

monthly = u["monthly"]
if not monthly.empty:
    total_out = monthly["qty"].sum()
    active_months = len(monthly[monthly["qty"] > 0])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total barang keluar", fmt_num(total_out))
    c2.metric("Rata-rata / bulan", fmt_num(total_out / active_months if active_months else 0))
    c3.metric("Dokumen NPBG", fmt_num(monthly["dokumen"].sum()))
    fig = px.bar(monthly, x="ym", y="qty", title="Konsumsi per bulan (qty NPBG)")
    fig.update_layout(height=320, xaxis_title="", yaxis_title="Qty", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width='stretch')

st.divider()
c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Per Divisi")
    d = u["by_divisi"]
    if not d.empty:
        st.plotly_chart(px.bar(d.head(15), x="qty", y="divisi", orientation="h").update_layout(
            height=380, yaxis_title="", xaxis_title="Qty", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"),
            width='stretch')
with c2:
    st.markdown("#### Per Klasifikasi")
    d = u["by_klasifikasi"]
    if not d.empty:
        st.plotly_chart(px.bar(d, x="qty", y="klasifikasi", orientation="h").update_layout(
            height=380, yaxis_title="", xaxis_title="Qty", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"),
            width='stretch')

st.divider()
st.markdown("#### Barang paling banyak keluar (Top 50)")
ti = u["top_items"].copy()
if not ti.empty:
    ti.columns = ["Deskripsi", "Kode", "Total Qty", "Baris NPBG", "Match"]
    st.dataframe(ti, width='stretch', hide_index=True)
    st.caption("Baris dengan Match ≠ MATCHED belum terhubung pasti ke master — selesaikan di Data Management → Matching Review.")

with st.expander("Per Pelanggan (Top 30)"):
    st.dataframe(u["by_pelanggan"], width='stretch', hide_index=True)
