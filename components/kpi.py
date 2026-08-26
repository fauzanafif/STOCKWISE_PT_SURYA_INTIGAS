"""KPI cards for the currently filtered dataset."""
import streamlit as st

from utils.calculations import STATUS_TIDAK_AMAN


def render_kpis(df):
    total_barang = len(df)
    barang_aman = int((df["Status"] != STATUS_TIDAK_AMAN).sum())
    barang_tidak_aman = int((df["Status"] == STATUS_TIDAK_AMAN).sum())
    total_stok = df["Sisa Stok"].sum()
    total_safety = df["Safety Stock"].sum()
    total_defisit = df["Defisit"].sum()

    row1 = st.columns(3)
    row1[0].metric("Total Barang", f"{total_barang:,}")
    row1[1].metric("Barang Aman", f"{barang_aman:,}", delta=None)
    row1[2].metric("Barang Tidak Aman", f"{barang_tidak_aman:,}")

    row2 = st.columns(3)
    row2[0].metric("Total Stok", f"{total_stok:,.0f}")
    row2[1].metric("Total Safety Stock", f"{total_safety:,.0f}")
    row2[2].metric("Defisit Stok", f"{total_defisit:,.0f}")
