"""STOCKWISE — Inventory dashboard: upload, edit, recalculate, visualize."""
import pandas as pd
import streamlit as st

from components.charts import (
    category_status_bar,
    lead_time_scatter,
    stock_vs_safety_bar,
    status_donut,
    top_deficit_bar,
    warehouse_stock_bar,
    warehouse_status_bar,
)
from components.data_editor import render_data_editor
from components.kpi import render_kpis
from utils.calculations import STATUS_TIDAK_AMAN, recalculate, suggest_lead_time_threshold
from utils.excel_handler import load_excel, to_export_bytes
from utils.insights import generate_insights

st.set_page_config(page_title="STOCKWISE", page_icon="📦", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {
        background: rgba(127, 127, 127, 0.06);
        border: 1px solid rgba(127, 127, 127, 0.15);
        border-radius: 10px;
        padding: 12px 16px;
    }
    .stockwise-insight {
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 8px;
        border: 1px solid rgba(127, 127, 127, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state():
    for key, default in [
        ("df", None),
        ("file_signature", None),
        ("lead_time_threshold", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def filter_signature(filters: dict) -> str:
    """A stable string key for the current filter combination.

    st.data_editor keeps its own internal state per widget `key`; if the key
    stays fixed while the underlying row set changes shape (a filter changed),
    Streamlit can keep showing the editor's stale internal state instead of
    the newly filtered rows. Deriving the key from the filters forces a fresh
    widget whenever the visible row set actually changes, while edits already
    made are safe because they were merged into full_df before this reruns.
    """
    parts = []
    for k in sorted(filters):
        v = filters[k]
        if isinstance(v, (list, tuple)):
            v = tuple(sorted(v))
        parts.append(f"{k}={v}")
    return "|".join(parts)


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df
    if filters["kategori_induk"]:
        result = result[result["Kategori Induk"].isin(filters["kategori_induk"])]
    if filters["kategori_anak1"]:
        result = result[result["Kategori Anak 1"].isin(filters["kategori_anak1"])]
    if filters["gudang"]:
        result = result[result["Letak Gudang"].isin(filters["gudang"])]
    if filters["status"]:
        result = result[result["Status"].isin(filters["status"])]
    if filters["kode_search"]:
        result = result[result["Kode Barang"].astype(str).str.contains(filters["kode_search"], case=False, na=False)]
    if filters["desk_search"]:
        result = result[
            result["Deskripsi Barang"].astype(str).str.contains(filters["desk_search"], case=False, na=False)
        ]
    lt_min, lt_max = filters["lead_time_range"]
    result = result[(result["Lead Time"] >= lt_min) & (result["Lead Time"] <= lt_max)]
    return result


def _non_blank_options(df: pd.DataFrame, col: str) -> list:
    return sorted(v for v in df[col].dropna().unique() if str(v).strip())


def render_sidebar(df: pd.DataFrame):
    st.sidebar.header("Filter")

    kategori_induk = st.sidebar.multiselect("Kategori Induk", _non_blank_options(df, "Kategori Induk"))
    kategori_anak1 = st.sidebar.multiselect("Kategori Anak 1", _non_blank_options(df, "Kategori Anak 1"))
    gudang = st.sidebar.multiselect("Letak Gudang", _non_blank_options(df, "Letak Gudang"))
    status = st.sidebar.multiselect("Status", _non_blank_options(df, "Status"))
    kode_search = st.sidebar.text_input("Cari Kode Barang")
    desk_search = st.sidebar.text_input("Cari Deskripsi Barang")

    lt_min_data = int(df["Lead Time"].min()) if not df.empty else 0
    lt_max_data = int(df["Lead Time"].max()) if not df.empty else 0
    if lt_min_data == lt_max_data:
        lt_max_data = lt_min_data + 1
    lead_time_range = st.sidebar.slider("Range Lead Time", lt_min_data, lt_max_data, (lt_min_data, lt_max_data))

    st.sidebar.divider()
    st.sidebar.header("Pengaturan Prioritas")
    if st.session_state.lead_time_threshold is None:
        st.session_state.lead_time_threshold = suggest_lead_time_threshold(df)
    st.session_state.lead_time_threshold = st.sidebar.number_input(
        "Ambang Lead Time Tinggi",
        min_value=0,
        value=int(st.session_state.lead_time_threshold),
        step=1,
        help="Barang TIDAK AMAN dengan Lead Time >= nilai ini dianggap PRIORITAS TINGGI.",
    )

    return {
        "kategori_induk": kategori_induk,
        "kategori_anak1": kategori_anak1,
        "gudang": gudang,
        "status": status,
        "kode_search": kode_search,
        "desk_search": desk_search,
        "lead_time_range": lead_time_range,
    }


def merge_edits(full_df: pd.DataFrame, filtered_view: pd.DataFrame, edited_view: pd.DataFrame) -> pd.DataFrame:
    """Fold edits made on a filtered subset back into the full dataset.

    Rows added in the editor get their index reassigned before merging: the
    editor numbers new rows relative to the filtered subset, so those indices
    can collide with unrelated rows in full_df that were filtered out.
    """
    full_df = full_df.copy()
    shared_cols = [c for c in edited_view.columns if c in full_df.columns]

    common_idx = filtered_view.index.intersection(edited_view.index)
    if len(common_idx) > 0:
        full_df.loc[common_idx, shared_cols] = edited_view.loc[common_idx, shared_cols]

    deleted_idx = filtered_view.index.difference(edited_view.index)
    if len(deleted_idx) > 0:
        full_df = full_df.drop(index=deleted_idx)

    added_idx = edited_view.index.difference(filtered_view.index)
    if len(added_idx) > 0:
        new_rows = edited_view.loc[added_idx].copy()
        start = (full_df.index.max() + 1) if len(full_df) > 0 else 0
        new_rows.index = range(start, start + len(new_rows))
        full_df = pd.concat([full_df, new_rows], axis=0)

    return full_df.reset_index(drop=True)


def render_insight_cards(insights):
    palette = {
        "success": ("#0ca30c", "rgba(12,163,12,0.08)"),
        "warning": ("#c98500", "rgba(201,133,0,0.10)"),
        "error": ("#d03b3b", "rgba(208,59,59,0.08)"),
        "info": ("#52514e", "rgba(127,127,127,0.08)"),
    }
    for severity, message in insights:
        color, bg = palette.get(severity, palette["info"])
        st.markdown(
            f'<div class="stockwise-insight" style="border-left: 4px solid {color}; background: {bg};">{message}</div>',
            unsafe_allow_html=True,
        )


def main():
    init_state()

    st.title("📦 STOCKWISE")
    st.caption("Dashboard inventory — upload, edit, dan analisis stok secara reaktif.")

    st.sidebar.header("Data")
    uploaded = st.sidebar.file_uploader("Upload Excel Inventory", type=["xlsx", "xls"])

    if uploaded is not None:
        signature = f"{uploaded.name}-{uploaded.size}"
        if signature != st.session_state.file_signature:
            df, error = load_excel(uploaded)
            if error:
                st.error(error)
                st.stop()
            st.session_state.lead_time_threshold = suggest_lead_time_threshold(df)
            df = recalculate(df, st.session_state.lead_time_threshold)
            st.session_state.df = df
            st.session_state.file_signature = signature

    if st.session_state.df is None:
        st.info("👈 Silakan upload file Excel inventory (.xlsx / .xls) melalui sidebar untuk memulai.")
        st.stop()

    full_df = st.session_state.df
    filters = render_sidebar(full_df)
    filtered_view = apply_filters(full_df, filters)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🗂️ Data Inventory", "🚚 Procurement", "⬇️ Export"])

    with tab2:
        st.subheader("Data Inventory")
        st.caption("Edit langsung di tabel. Selisih, Status, dan kolom analisis lain dihitung ulang otomatis.")
        editor_key = f"inventory_editor::{filter_signature(filters)}"
        edited_view = render_data_editor(filtered_view, options_df=full_df, key=editor_key)
        full_df = merge_edits(full_df, filtered_view, edited_view)
        full_df = recalculate(full_df, st.session_state.lead_time_threshold)
        st.session_state.df = full_df

    filtered_final = apply_filters(full_df, filters)

    with tab1:
        st.subheader("Ringkasan Inventory")
        render_kpis(filtered_final)

        st.divider()
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("**Status Inventory**")
            fig = status_donut(filtered_final)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("**Top Barang dengan Defisit Terbesar**")
            fig = top_deficit_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.success("Tidak ada barang dengan defisit stok.")

        st.markdown("**Stok vs Safety Stock (Top Defisit)**")
        fig = stock_vs_safety_bar(filtered_final)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Inventory per Gudang — Status**")
            fig = warehouse_status_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("**Inventory per Gudang — Stok vs Safety Stock**")
            fig = warehouse_stock_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
        with c4:
            st.markdown("**Inventory per Kategori Induk**")
            fig = category_status_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("**Lead Time vs Defisit**")
            fig = lead_time_scatter(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("Inventory Insight")
        insights = generate_insights(filtered_final, st.session_state.lead_time_threshold)
        render_insight_cards(insights)

    with tab3:
        st.subheader("Procurement Priority")
        unsafe = filtered_final[filtered_final["Status"] == STATUS_TIDAK_AMAN].sort_values(
            "Priority Score", ascending=False
        )
        if unsafe.empty:
            st.success("✅ Tidak ada barang yang memerlukan procurement segera.")
        else:
            cols = [
                "Kode Barang",
                "Deskripsi Barang",
                "Letak Gudang",
                "Safety Stock",
                "Sisa Stok",
                "Defisit",
                "Lead Time",
                "Priority Score",
                "Priority Level",
                "Rekomendasi",
            ]
            cols = [c for c in cols if c in unsafe.columns]
            st.dataframe(unsafe[cols], use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("Export Data")
        st.caption("Hasil export sudah mencakup Selisih, Status, Defisit, Priority Score/Level, dan Rekomendasi.")

        export_scope = st.radio("Data yang diexport", ["Seluruh Data", "Data Terfilter"], horizontal=True)
        export_df = full_df if export_scope == "Seluruh Data" else filtered_final

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Download Excel",
                data=to_export_bytes(export_df),
                file_name="stockwise_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "⬇️ Download CSV",
                data=export_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="stockwise_export.csv",
                mime="text/csv",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
