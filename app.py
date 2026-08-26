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
from utils.excel_handler import build_template_bytes, load_excel, to_export_bytes
from utils.insights import generate_insights
from utils.theme import COLOR_AMAN, COLOR_NEUTRAL, COLOR_TIDAK_AMAN, COLOR_WARNING

st.set_page_config(page_title="STOCKWISE", page_icon="📦", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }

    .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1300px;}

    /* ---- App header ---- */
    .sw-hero {
        display: flex; align-items: center; gap: 14px;
        margin-bottom: 0.25rem;
    }
    .sw-hero .sw-hero-emoji {
        font-size: 2.1rem; line-height: 1;
    }
    .sw-hero h1 { margin: 0; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; }
    .sw-hero-caption { color: #898781; font-size: 0.95rem; margin: 2px 0 1.2rem 0; }

    /* ---- Section headers ---- */
    .sw-section-title {
        font-size: 1.15rem; font-weight: 700; margin: 0 0 2px 0; letter-spacing: -0.01em;
    }
    .sw-section-caption { color: #898781; font-size: 0.85rem; margin-bottom: 0.6rem; }
    .sw-chart-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0px; }
    .sw-chart-caption { color: #898781; font-size: 0.78rem; margin-bottom: 6px; }

    /* ---- KPI cards ---- */
    .sw-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 12px;
        margin-bottom: 18px;
    }
    .sw-kpi-card {
        display: flex; align-items: center; gap: 12px;
        background: rgba(127, 127, 127, 0.06);
        border: 1px solid rgba(127, 127, 127, 0.14);
        border-radius: 14px;
        padding: 14px 16px;
        transition: border-color 0.15s ease;
    }
    .sw-kpi-card:hover { border-color: rgba(127, 127, 127, 0.3); }
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
        background: rgba(127, 127, 127, 0.15);
        overflow: hidden;
    }
    .sw-health-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }

    /* ---- Insight cards ---- */
    .sw-insight {
        display: flex; gap: 10px; align-items: flex-start;
        padding: 12px 14px;
        border-radius: 10px;
        margin-bottom: 8px;
        border: 1px solid rgba(127, 127, 127, 0.14);
        font-size: 0.92rem;
        line-height: 1.4;
    }

    /* ---- Tabs ---- */
    button[data-baseweb="tab"] { font-size: 0.98rem; font-weight: 600; padding: 8px 4px; }
    div[data-testid="stMetric"] {
        background: rgba(127, 127, 127, 0.06);
        border: 1px solid rgba(127, 127, 127, 0.15);
        border-radius: 10px;
        padding: 12px 16px;
    }

    /* ---- Welcome / empty state ---- */
    .sw-welcome-feature {
        background: rgba(127, 127, 127, 0.05);
        border: 1px solid rgba(127, 127, 127, 0.12);
        border-radius: 12px;
        padding: 14px 16px;
        height: 100%;
    }
    .sw-welcome-feature .emoji { font-size: 1.4rem; }
    .sw-welcome-feature b { display: block; margin: 6px 0 2px 0; font-size: 0.95rem; }
    .sw-welcome-feature p { margin: 0; font-size: 0.82rem; color: #898781; line-height: 1.4; }
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
        STOCKWISE membantu Anda memantau stok gudang secara real-time: upload Excel inventory,
        edit datanya langsung di tabel, dan dashboard — KPI, chart, insight, sampai rekomendasi
        procurement — akan ter-update otomatis tanpa perlu refresh halaman.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    features = [
        ("📤", "Upload & Auto-Detect", "Baca file Excel Anda apa adanya — header boleh tidak di baris pertama."),
        ("✏️", "Edit Langsung", "Ubah Safety Stock / Sisa Stok di tabel, semua kalkulasi ikut ter-update."),
        ("📊", "KPI & Chart Otomatis", "Lihat kondisi inventory dari berbagai sudut: gudang, kategori, lead time."),
        ("🚨", "Insight & Rekomendasi", "Sistem otomatis menandai barang yang perlu diprioritaskan untuk dibeli."),
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
    st.info("👈 **Mulai dengan meng-upload file Excel inventory Anda** di sidebar sebelah kiri.")

    st.markdown("##### Belum punya file? Unduh template berikut untuk memulai:")
    st.download_button(
        "📥 Download Template Excel",
        data=build_template_bytes(),
        file_name="template_stockwise.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="template_download_welcome",
    )
    st.caption(
        "Template sudah mengikuti format kolom yang didukung (termasuk contoh format "
        "`Sisa Stok` seperti \"STOK 15 PCS\"), lengkap dengan 2 baris contoh data."
    )


def main():
    init_state()

    st.markdown(
        '<div class="sw-hero"><span class="sw-hero-emoji">📦</span><h1>STOCKWISE</h1></div>'
        '<div class="sw-hero-caption">Dashboard inventory — upload, edit, dan analisis stok secara reaktif, '
        'tanpa perlu refresh halaman.</div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("### 📁 Data")
    uploaded = st.sidebar.file_uploader("Upload Excel Inventory", type=["xlsx", "xls"])
    st.sidebar.download_button(
        "📥 Download Template Excel",
        data=build_template_bytes(),
        file_name="template_stockwise.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help="Belum punya file? Unduh template kosong dengan format kolom yang sesuai.",
        key="template_download_sidebar",
    )

    if uploaded is not None:
        signature = f"{uploaded.name}-{uploaded.size}"
        if signature != st.session_state.file_signature:
            with st.spinner("Membaca dan memproses file Excel..."):
                df, error = load_excel(uploaded)
            if error:
                st.error(error)
                st.stop()
            st.session_state.lead_time_threshold = suggest_lead_time_threshold(df)
            df = recalculate(df, st.session_state.lead_time_threshold)
            st.session_state.df = df
            st.session_state.file_signature = signature
            st.session_state.file_name = uploaded.name
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
            "Edit langsung di tabel — Selisih, Status, Defisit, Priority, dan Rekomendasi otomatis dihitung ulang.",
        )
        n_tidak_aman = int((filtered_view["Status"] == STATUS_TIDAK_AMAN).sum())
        st.caption(
            f"Menampilkan **{len(filtered_view):,}** dari **{len(full_df):,}** barang sesuai filter aktif "
            f"— **{n_tidak_aman:,}** di antaranya TIDAK AMAN."
        )
        editor_key = f"inventory_editor::{filter_signature(filters)}"
        edited_view = render_data_editor(filtered_view, options_df=full_df, key=editor_key)
        full_df = merge_edits(full_df, filtered_view, edited_view)
        full_df = recalculate(full_df, st.session_state.lead_time_threshold)
        st.session_state.df = full_df

    filtered_final = apply_filters(full_df, filters)

    with tab1:
        render_section_header("Ringkasan Inventory", "Kondisi stok Anda saat ini, berdasarkan filter yang aktif.")
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
        render_section_header("💡 Inventory Insight", "Ringkasan otomatis dari data yang sedang aktif.")
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

            styled = unsafe[cols].style.applymap(_style_priority, subset=["Priority Level"])
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
