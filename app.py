"""STOCKWISE — Inventory dashboard: upload, edit, recalculate, visualize."""
import base64
from pathlib import Path

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
from utils.excel_handler import build_template_bytes, load_dropdown_options, load_excel, to_export_bytes
from utils.insights import generate_insights
from utils.theme import COLOR_AMAN, COLOR_NEUTRAL, COLOR_TIDAK_AMAN, COLOR_WARNING

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"


@st.cache_data
def _logo_data_uri() -> str:
    """Base64 data URI for the company logo, so it can be embedded directly in
    injected HTML (a plain relative <img src> won't load — Streamlit doesn't
    serve arbitrary local files over HTTP)."""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


st.set_page_config(page_title="STOCKWISE", page_icon=str(LOGO_PATH), layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --sw-blue: #2a78d6;
        --sw-blue-dark: #14328c;
        --sw-blue-tint-06: rgba(20, 60, 160, 0.055);
        --sw-blue-tint-12: rgba(20, 60, 160, 0.10);
        --sw-blue-tint-20: rgba(20, 60, 160, 0.18);
        --sw-blue-tint-30: rgba(20, 60, 160, 0.32);
    }

    html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }

    .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1300px;}

    [data-testid="stAppViewContainer"] > .main {
        background: linear-gradient(180deg, rgba(42, 120, 214, 0.05) 0%, rgba(42, 120, 214, 0) 260px);
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid var(--sw-blue-tint-20);
    }
    [data-testid="stSidebar"] h2 { color: var(--sw-blue-dark); font-size: 1.02rem; }

    /* ---- App header ---- */
    .sw-hero {
        display: flex; align-items: center; gap: 14px;
        margin-bottom: 0.25rem;
    }
    .sw-hero .sw-hero-logo {
        height: 42px; width: 42px; object-fit: contain;
    }
    .sw-hero h1 { margin: 0; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; color: var(--sw-blue-dark); }
    .sw-hero-caption { color: #5b6b8c; font-size: 0.95rem; margin: 2px 0 1.2rem 0; }

    /* ---- Section headers ---- */
    .sw-section-title {
        font-size: 1.15rem; font-weight: 700; margin: 0 0 2px 0; letter-spacing: -0.01em;
        padding-left: 10px; border-left: 4px solid var(--sw-blue); color: var(--sw-blue-dark);
    }
    .sw-section-caption { color: #5b6b8c; font-size: 0.85rem; margin-bottom: 0.6rem; padding-left: 10px; }
    .sw-chart-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0px; }
    .sw-chart-caption { color: #5b6b8c; font-size: 0.78rem; margin-bottom: 6px; }

    /* ---- KPI cards ---- */
    .sw-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 12px;
        margin-bottom: 18px;
    }
    .sw-kpi-card {
        display: flex; align-items: center; gap: 12px;
        background: var(--sw-blue-tint-06);
        border: 1px solid var(--sw-blue-tint-20);
        border-top: 3px solid var(--sw-blue-tint-30);
        border-radius: 14px;
        padding: 14px 16px;
        transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .sw-kpi-card:hover { border-color: var(--sw-blue-tint-30); transform: translateY(-1px); }
    .sw-kpi-icon {
        flex-shrink: 0;
        width: 42px; height: 42px;
        border-radius: 11px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.25rem;
    }
    .sw-kpi-label { font-size: 0.78rem; font-weight: 600; opacity: 0.75; text-transform: uppercase; letter-spacing: 0.03em; }
    .sw-kpi-value { font-size: 1.55rem; font-weight: 800; line-height: 1.25; }
    .sw-kpi-sub { font-size: 0.72rem; opacity: 0.6; }

    /* ---- Health bar ---- */
    .sw-health { margin: 4px 0 22px 0; }
    .sw-health-label {
        display: flex; justify-content: space-between; align-items: baseline;
        font-size: 0.85rem; font-weight: 600; margin-bottom: 6px;
    }
    .sw-health-pct { font-weight: 800; }
    .sw-health-track {
        width: 100%; height: 10px; border-radius: 999px;
        background: var(--sw-blue-tint-12);
        overflow: hidden;
    }
    .sw-health-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }

    /* ---- Insight cards ---- */
    .sw-insight {
        display: flex; gap: 10px; align-items: flex-start;
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 8px;
        border: 1px solid var(--sw-blue-tint-20);
        font-size: 0.92rem;
        line-height: 1.4;
    }

    /* ---- Tabs ---- */
    button[data-baseweb="tab"] { font-size: 0.98rem; font-weight: 600; padding: 8px 4px; }
    button[data-baseweb="tab"][aria-selected="true"] { color: var(--sw-blue-dark); }
    div[data-testid="stMetric"] {
        background: var(--sw-blue-tint-06);
        border: 1px solid var(--sw-blue-tint-20);
        border-radius: 10px;
        padding: 12px 16px;
    }

    /* ---- Welcome / empty state ---- */
    .sw-welcome-feature {
        background: var(--sw-blue-tint-06);
        border: 1px solid var(--sw-blue-tint-12);
        border-radius: 12px;
        padding: 14px 16px;
        height: 100%;
        transition: border-color 0.15s ease;
    }
    .sw-welcome-feature:hover { border-color: var(--sw-blue-tint-30); }
    .sw-welcome-feature .emoji { font-size: 1.4rem; }
    .sw-welcome-feature b { display: block; margin: 6px 0 2px 0; font-size: 0.95rem; color: var(--sw-blue-dark); }
    .sw-welcome-feature p { margin: 0; font-size: 0.82rem; color: #5b6b8c; line-height: 1.4; }

    /* ---- Sidebar brand ---- */
    @keyframes sw-brand-fade {
        from { opacity: 0; transform: translateY(-6px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes sw-brand-glow {
        0%, 100% { box-shadow: 0 0 0 1px rgba(20, 50, 140, 0.18), 0 0 0 0 rgba(20, 50, 140, 0.35), 0 6px 16px rgba(20, 50, 140, 0.22); }
        50% { box-shadow: 0 0 0 1px rgba(20, 50, 140, 0.18), 0 0 0 8px rgba(20, 50, 140, 0), 0 6px 16px rgba(20, 50, 140, 0.22); }
    }
    .sw-sidebar-brand {
        display: flex; flex-direction: column; align-items: center;
        gap: 10px;
        padding: 4px 0 18px 0;
        margin-bottom: 10px;
        border-bottom: 1px solid var(--sw-blue-tint-20);
        animation: sw-brand-fade 0.5s ease;
    }
    .sw-sidebar-brand img {
        height: 64px; width: 64px; object-fit: contain;
        border-radius: 50%;
        background: #fff;
        padding: 7px;
        animation: sw-brand-glow 2.8s ease-in-out infinite;
        transition: transform 0.25s ease;
    }
    .sw-sidebar-brand img:hover {
        transform: scale(1.08) rotate(-3deg);
    }
    .sw-sidebar-brand-name {
        font-weight: 800; font-size: 0.85rem; letter-spacing: 0.07em;
        text-align: center; text-transform: uppercase;
        color: #14328c;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state():
    for key, default in [
        ("df", None),
        ("file_signature", None),
        ("file_name", None),
        ("lead_time_threshold", None),
        ("debug_info", None),
        ("dropdown_options", {}),
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
    if filters["kategori_anak2"]:
        result = result[result["Kategori Anak 2"].isin(filters["kategori_anak2"])]
    if filters["kategori_anak3"]:
        result = result[result["Kategori Anak 3"].isin(filters["kategori_anak3"])]
    if filters["uom"]:
        result = result[result["UoM"].isin(filters["uom"])]
    if filters["gudang"]:
        result = result[result["Letak Gudang"].isin(filters["gudang"])]
    if filters["status"]:
        result = result[result["Status"].isin(filters["status"])]
    if filters["perlu_blueprint"]:
        result = result[result["Perlu Blueprint?"].isin(filters["perlu_blueprint"])]
    if filters["kode_search"]:
        result = result[result["Kode Barang"].astype(str).str.contains(filters["kode_search"], case=False, na=False)]
    if filters["desk_search"]:
        result = result[
            result["Deskripsi Barang"].astype(str).str.contains(filters["desk_search"], case=False, na=False)
        ]
    lt_min, lt_max = filters["lead_time_range"]
    result = result[(result["Lead Time"] >= lt_min) & (result["Lead Time"] <= lt_max)]
    return result


def _filter_options(df: pd.DataFrame, col: str, extra_options: dict = None) -> list:
    """Unique non-blank values for a filter, unioned with choices from the
    workbook's "Dropdown List" sheet (if any) so the filter isn't limited to
    values that happen to already be present in the uploaded data.
    """
    values = set(v for v in df[col].dropna().unique() if str(v).strip()) if col in df.columns else set()
    if extra_options:
        values |= {str(v).strip() for v in extra_options.get(col, []) if str(v).strip()}
    return sorted(values)


def render_sidebar(df: pd.DataFrame):
    st.sidebar.header("Filter")
    dropdown_options = st.session_state.dropdown_options

    kategori_induk = st.sidebar.multiselect(
        "Kategori Induk", _filter_options(df, "Kategori Induk", dropdown_options)
    )
    kategori_anak1 = st.sidebar.multiselect(
        "Kategori Anak 1", _filter_options(df, "Kategori Anak 1", dropdown_options)
    )
    kategori_anak2 = st.sidebar.multiselect(
        "Kategori Anak 2", _filter_options(df, "Kategori Anak 2", dropdown_options)
    )
    kategori_anak3 = st.sidebar.multiselect(
        "Kategori Anak 3", _filter_options(df, "Kategori Anak 3", dropdown_options)
    )
    uom = st.sidebar.multiselect("UoM", _filter_options(df, "UoM", dropdown_options))
    gudang = st.sidebar.multiselect("Letak Gudang", _filter_options(df, "Letak Gudang"))
    status = st.sidebar.multiselect("Status", _filter_options(df, "Status"))
    perlu_blueprint = st.sidebar.multiselect("Perlu Blueprint?", _filter_options(df, "Perlu Blueprint?"))
    kode_search = st.sidebar.text_input("Cari Kode Barang")
    desk_search = st.sidebar.text_input("Cari Deskripsi Barang")

    lt_min_data = int(df["Lead Time"].min()) if not df.empty else 0
    lt_max_data = int(df["Lead Time"].max()) if not df.empty else 0

    st.sidebar.caption("Range Lead Time")
    lt_col1, lt_col2 = st.sidebar.columns(2)
    lt_min = lt_col1.number_input("Dari", min_value=0, value=lt_min_data, step=1, key="lead_time_filter_min")
    lt_max = lt_col2.number_input("Sampai", min_value=0, value=lt_max_data, step=1, key="lead_time_filter_max")
    lead_time_range = (lt_min, lt_max)

    st.sidebar.divider()
    st.sidebar.header("Pengaturan Prioritas")
    if st.session_state.lead_time_threshold is None:
        st.session_state.lead_time_threshold = suggest_lead_time_threshold(df)
    st.session_state.lead_time_threshold = st.sidebar.number_input(
        "Ambang Lead Time Tinggi",
        min_value=0,
        value=int(st.session_state.lead_time_threshold),
        step=1,
        help="Barang TIDAK AMAN dengan Lead Time >= nilai ini dianggap prioritas tinggi.",
    )

    return {
        "kategori_induk": kategori_induk,
        "kategori_anak1": kategori_anak1,
        "kategori_anak2": kategori_anak2,
        "kategori_anak3": kategori_anak3,
        "uom": uom,
        "gudang": gudang,
        "status": status,
        "perlu_blueprint": perlu_blueprint,
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
        "success": (COLOR_AMAN, "rgba(12,163,12,0.08)"),
        "warning": (COLOR_WARNING, "rgba(201,133,0,0.10)"),
        "error": (COLOR_TIDAK_AMAN, "rgba(208,59,59,0.08)"),
        "info": (COLOR_NEUTRAL, "rgba(127,127,127,0.08)"),
    }
    for severity, message in insights:
        color, bg = palette.get(severity, palette["info"])
        st.markdown(
            f'<div class="sw-insight" style="border-left: 4px solid {color}; background: {bg};">'
            f'<span>{message}</span></div>',
            unsafe_allow_html=True,
        )


def render_section_header(title: str, caption: str = ""):
    st.markdown(f'<div class="sw-section-title">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="sw-section-caption">{caption}</div>', unsafe_allow_html=True)


def render_chart_header(title: str, caption: str = ""):
    st.markdown(f'<div class="sw-chart-title">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="sw-chart-caption">{caption}</div>', unsafe_allow_html=True)


def render_welcome():
    st.markdown(
        """
        <div style="padding: 6px 0 18px 0;">
        <p style="font-size: 1rem; opacity: 0.85; max-width: 720px;">
        Upload Excel inventory kamu, edit langsung di tabel, dan sisanya — KPI, chart, insight,
        rekomendasi pembelian — ikut update sendiri. Gak perlu refresh.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    features = [
        ("📤", "Upload apa adanya", "Header gak harus di baris pertama, file kamu bisa langsung dipakai."),
        ("✏️", "Edit di tabel", "Ubah Safety Stock atau Sisa Stok, kalkulasi lain ikut nyesuain."),
        ("📊", "KPI & chart otomatis", "Lihat kondisi stok dari sisi gudang, kategori, sampai lead time."),
        ("🚨", "Insight & rekomendasi", "Langsung kelihatan barang mana yang paling perlu dibeli duluan."),
    ]
    cols = st.columns(4)
    for col, (icon, title, desc) in zip(cols, features):
        with col:
            st.markdown(
                f'<div class="sw-welcome-feature"><span class="emoji">{icon}</span>'
                f'<b>{title}</b><p>{desc}</p></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    st.info("👈 Upload file Excel-nya dulu di sidebar sebelah kiri.")

    st.markdown("##### Belum punya file? Pakai template ini aja:")
    st.download_button(
        "📥 Download Template Excel",
        data=build_template_bytes(),
        file_name="template_stockwise.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="template_download_welcome",
    )
    st.caption(
        "Formatnya udah sesuai, termasuk contoh Sisa Stok kayak \"STOK 15 PCS\" — tinggal isi datanya."
    )


def main():
    init_state()

    st.markdown(
        f'<div class="sw-hero"><img class="sw-hero-logo" src="{_logo_data_uri()}"><h1>STOCKWISE</h1></div>'
        '<div class="sw-hero-caption">Upload, edit, pantau stok dan semuanya update otomatis, gak perlu refresh.</div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        f'<div class="sw-sidebar-brand">'
        f'<img src="{_logo_data_uri()}" alt="Logo PT Surya Inti Gas">'
        f'<div class="sw-sidebar-brand-name">PT Surya Inti Gas</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.sidebar.file_uploader("Upload Excel Inventory", type=["xlsx", "xls"])
    st.sidebar.download_button(
        "📥 Download Template Excel",
        data=build_template_bytes(),
        file_name="template_stockwise.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help="Belum punya file? Ini template kosong yang formatnya udah sesuai.",
        key="template_download_sidebar",
    )

    if uploaded is not None:
        signature = f"{uploaded.name}-{uploaded.size}"
        if signature != st.session_state.file_signature:
            with st.spinner("Membaca dan memproses file Excel..."):
                df, error, debug_info = load_excel(uploaded)
            st.session_state.debug_info = debug_info
            if error:
                st.error(error)
                if debug_info.get("all_sheets"):
                    with st.expander("🐞 Debug Excel"):
                        st.write("Sheet terdeteksi:", debug_info.get("all_sheets"))
                        st.write("Sheet yang dipilih:", debug_info.get("sheet"))
                        st.write("Baris header:", debug_info.get("header_row"))
                        st.write("Kolom terbaca:", debug_info.get("columns"))
                st.stop()
            st.session_state.lead_time_threshold = suggest_lead_time_threshold(df)
            df = recalculate(df, st.session_state.lead_time_threshold)
            st.session_state.df = df
            st.session_state.file_signature = signature
            st.session_state.file_name = uploaded.name
            st.session_state.dropdown_options = load_dropdown_options(uploaded)
            st.toast(f"Berhasil memuat {len(df):,} barang dari '{uploaded.name}'.", icon="✅")

    if st.session_state.df is None:
        render_welcome()
        st.stop()

    full_df = st.session_state.df
    st.sidebar.caption(f"📄 **{st.session_state.file_name}** — {len(full_df):,} barang")
    st.sidebar.divider()

    filters = render_sidebar(full_df)
    filtered_view = apply_filters(full_df, filters)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🗂️ Data Inventory", "🚚 Procurement", "⬇️ Export"])

    with tab2:
        render_section_header(
            "Data Inventory",
            "Edit langsung di tabel — Selisih, Status, Defisit, Priority, dan Rekomendasi ikut kehitung ulang.",
        )
        n_tidak_aman = int((filtered_view["Status"] == STATUS_TIDAK_AMAN).sum())
        st.caption(
            f"Nampilin **{len(filtered_view):,}** dari **{len(full_df):,}** barang sesuai filter "
            f"— **{n_tidak_aman:,}** di antaranya TIDAK AMAN."
        )
        debug_info = st.session_state.debug_info
        if debug_info:
            with st.expander("🐞 Debug Excel"):
                st.write("Sheet terdeteksi pada workbook:", debug_info.get("all_sheets"))
                st.write("Sheet yang digunakan:", debug_info.get("sheet"))
                st.write("Baris header:", debug_info.get("header_row"))
                st.write("Kolom terdeteksi:", debug_info.get("columns"))
                st.write("Pilihan dropdown dari sheet 'Dropdown List':", st.session_state.dropdown_options or "(tidak ditemukan)")

        editor_key = f"inventory_editor::{filter_signature(filters)}"
        edited_view = render_data_editor(
            filtered_view,
            options_df=full_df,
            extra_options=st.session_state.dropdown_options,
            key=editor_key,
        )
        full_df = merge_edits(full_df, filtered_view, edited_view)
        full_df = recalculate(full_df, st.session_state.lead_time_threshold)
        st.session_state.df = full_df

    filtered_final = apply_filters(full_df, filters)

    with tab1:
        render_section_header("Ringkasan Inventory", "Kondisi stok berdasarkan filter yang aktif.")
        render_kpis(filtered_final)

        st.divider()
        render_section_header("🔎 Kondisi Inventory Saat Ini", "Apa yang aman, apa yang tidak, dan seberapa parah.")
        c1, c2 = st.columns([1, 2])
        with c1:
            render_chart_header("Status Inventory", "Proporsi barang AMAN vs TIDAK AMAN.")
            fig = status_donut(filtered_final)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            render_chart_header("Top Barang dengan Defisit Terbesar", "Barang paling kurang dari safety stock-nya.")
            fig = top_deficit_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.success("✅ Tidak ada barang dengan defisit stok.")

        render_chart_header("Stok vs Safety Stock", "Perbandingan langsung: stok saat ini vs batas amannya.")
        fig = stock_vs_safety_bar(filtered_final)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        render_section_header("📍 Analisis per Lokasi & Kategori", "Di gudang atau kategori mana masalah paling banyak.")
        c3, c4 = st.columns(2)
        with c3:
            render_chart_header("Inventory per Gudang — Status", "Jumlah barang aman/tidak aman di tiap gudang.")
            fig = warehouse_status_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            render_chart_header("Inventory per Gudang — Stok vs Safety Stock", "Total stok vs total safety stock per gudang.")
            fig = warehouse_stock_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
        with c4:
            render_chart_header("Inventory per Kategori Induk", "Jumlah barang aman/tidak aman per kategori.")
            fig = category_status_bar(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            render_chart_header("Lead Time vs Defisit", "Barang lead time tinggi + defisit besar = prioritas procurement.")
            fig = lead_time_scatter(filtered_final)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        render_section_header("💡 Inventory Insight", "Ringkasan singkat dari data yang lagi ditampilkan.")
        insights = generate_insights(filtered_final, st.session_state.lead_time_threshold)
        render_insight_cards(insights)

    with tab3:
        render_section_header(
            "Procurement Priority",
            "Barang TIDAK AMAN, diurutkan dari yang paling mendesak untuk dibeli.",
        )
        unsafe = filtered_final[filtered_final["Status"] == STATUS_TIDAK_AMAN].sort_values(
            "Priority Score", ascending=False
        )
        if unsafe.empty:
            st.success("✅ Tidak ada barang yang memerlukan procurement segera.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Barang Perlu Aksi", f"{len(unsafe):,}")
            m2.metric("Total Defisit", f"{unsafe['Defisit'].sum():,.0f}")
            m3.metric("Prioritas Tinggi", f"{(unsafe['Priority Level'] == 'HIGH').sum():,}")
            st.write("")

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

            priority_colors = {"HIGH": COLOR_TIDAK_AMAN, "MEDIUM": COLOR_WARNING, "LOW": COLOR_AMAN}

            def _style_priority(val):
                color = priority_colors.get(val)
                return f"background-color:{color}26; color:{color}; font-weight:700;" if color else ""

            styled = unsafe[cols].style.map(_style_priority, subset=["Priority Level"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab4:
        render_section_header(
            "Export Data",
            "Hasil export sudah mencakup Selisih, Status, Defisit, Priority Score/Level, dan Rekomendasi.",
        )

        export_scope = st.radio("Data yang diexport", ["Seluruh Data", "Data Terfilter"], horizontal=True)
        export_df = full_df if export_scope == "Seluruh Data" else filtered_final
        st.caption(f"Akan mengekspor **{len(export_df):,}** baris.")

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
