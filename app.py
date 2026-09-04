"""STOCKWISE — Inventory dashboard: upload, edit, recalculate, visualize."""
import base64
from pathlib import Path

import pandas as pd
import plotly.express as px
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
from utils.pdf_export import build_pdf_bytes
from utils.npbg_handler import NPBG_DISPLAY_COLUMNS, load_npbg, npbg_summary
from utils.ppb_handler import PPB_DISPLAY_COLUMNS, load_ppb, ppb_summary
from utils.theme import COLOR_AMAN, COLOR_NEUTRAL, COLOR_TIDAK_AMAN, COLOR_WARNING, SERIES_BLUE

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"


@st.cache_data
def _logo_data_uri() -> str:
    """Base64 data URI for the company logo, so it can be embedded directly in
    injected HTML (a plain relative <img src> won't load — Streamlit doesn't
    serve arbitrary local files over HTTP)."""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# Streamlit reruns the whole script — including every tab's body — on every
# interaction (upload, cell edit, filter change), whether or not the Export
# tab is the one actually visible. Without caching, building the Excel/PDF/CSV
# bytes (the PDF especially — it paginates every row into styled Paragraphs)
# would happen again on every single rerun. Caching on the export dataframe's
# content means it's only rebuilt when the data actually changes.
#
# show_spinner=False on purpose: this can fire in the background on any edit
# (even from the Dashboard tab, since tab4's code still runs every rerun), and
# the spinner is now a big full-screen overlay (see the CSS below) — showing
# that for a silent background cache rebuild the user never asked for is what
# was reported as the dashboard "ngebayang" (flashing/ghosting). The overlay
# is reserved for the one deliberate, user-initiated wait: the upload spinner.
@st.cache_data(show_spinner=False)
def _cached_excel_bytes(df: pd.DataFrame) -> bytes:
    return to_export_bytes(df)


@st.cache_data(show_spinner=False)
def _cached_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def _cached_pdf_bytes(df: pd.DataFrame, scope_label: str, file_name: str) -> bytes:
    return build_pdf_bytes(df, scope_label, file_name)


# Static content (no arguments) — still worth caching since it's otherwise
# rebuilt from scratch on every single rerun even though it never changes.
@st.cache_data(show_spinner=False)
def _cached_template_bytes() -> bytes:
    return build_template_bytes()


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
        box-shadow: 0 1px 2px rgba(20, 50, 140, 0.05), 0 6px 16px rgba(20, 50, 140, 0.04);
        transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
    }
    .sw-kpi-card:hover {
        border-color: var(--sw-blue-tint-30);
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(20, 50, 140, 0.10), 0 10px 24px rgba(20, 50, 140, 0.08);
    }
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
        box-shadow: 0 1px 2px rgba(20, 50, 140, 0.04);
        font-size: 0.92rem;
        line-height: 1.4;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .sw-insight:hover {
        transform: translateX(2px);
        box-shadow: 0 3px 10px rgba(20, 50, 140, 0.08);
    }

    /* ---- Tabs ---- */
    div[data-baseweb="tab-list"] { gap: 4px; }
    button[data-baseweb="tab"] {
        font-size: 0.98rem; font-weight: 600; padding: 8px 14px;
        border-radius: 8px 8px 0 0; transition: background 0.15s ease, color 0.15s ease;
    }
    button[data-baseweb="tab"]:hover { background: var(--sw-blue-tint-06); }
    button[data-baseweb="tab"][aria-selected="true"] { color: var(--sw-blue-dark); }
    div[data-baseweb="tab-highlight"] { background-color: var(--sw-blue); height: 3px; border-radius: 3px; }
    div[data-testid="stMetric"] {
        background: var(--sw-blue-tint-06);
        border: 1px solid var(--sw-blue-tint-20);
        border-radius: 10px;
        padding: 12px 16px;
    }

    /* ---- Chart & table cards ---- */
    /* This app only ever uses st.container(border=True) around a chart or the
       Procurement table, so it's safe to style every bordered container the
       same way — the dashboard reads as a grid of widgets instead of plots
       floating loose on the page. */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        border-color: var(--sw-blue-tint-20) !important;
        background: #ffffffa8;
        box-shadow: 0 1px 2px rgba(20, 50, 140, 0.05), 0 8px 20px rgba(20, 50, 140, 0.05);
        transition: box-shadow 0.15s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 4px 12px rgba(20, 50, 140, 0.10), 0 12px 28px rgba(20, 50, 140, 0.08);
    }

    /* ---- Welcome / empty state ---- */
    .sw-welcome-feature {
        background: var(--sw-blue-tint-06);
        border: 1px solid var(--sw-blue-tint-12);
        border-radius: 12px;
        padding: 14px 16px;
        height: 100%;
        box-shadow: 0 1px 2px rgba(20, 50, 140, 0.04);
        transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
    }
    .sw-welcome-feature:hover {
        border-color: var(--sw-blue-tint-30);
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(20, 50, 140, 0.08);
    }
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
        height: 92px; width: 92px; object-fit: contain;
        border-radius: 50%;
        background: #fff;
        padding: 9px;
        animation: sw-brand-glow 2.8s ease-in-out infinite;
        transition: transform 0.25s ease;
    }
    .sw-sidebar-brand img:hover {
        transform: scale(1.08) rotate(-3deg);
    }
    .sw-sidebar-brand-name {
        font-weight: 800; font-size: 1.05rem; letter-spacing: 0.06em;
        text-align: center; text-transform: uppercase;
        color: #14328c;
        line-height: 1.3;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Replace every st.spinner (upload processing, and the "show_spinner" cache
# messages on the export builders above) with a full-screen overlay of the
# company logo spinning in the center, instead of Streamlit's tiny default
# icon. This is a separate (f-string) markdown call — kept apart from the
# main CSS block above, which is a plain string full of literal braces that
# would otherwise all need escaping.
st.markdown(
    f"""
    <style>
    [data-testid="stSpinner"] {{
        position: fixed;
        inset: 0;
        z-index: 999999;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 18px;
        background: rgba(255, 255, 255, 0.88);
        backdrop-filter: blur(3px);
    }}
    [data-testid="stSpinner"] svg,
    [data-testid="stSpinner"] i {{
        display: none;
    }}
    [data-testid="stSpinner"]::before {{
        content: "";
        width: 76px;
        height: 76px;
        background: #fff url('{_logo_data_uri()}') center/contain no-repeat;
        border-radius: 50%;
        padding: 8px;
        box-shadow: 0 8px 24px rgba(20, 50, 140, 0.28);
        animation: sw-spin 1s linear infinite;
    }}
    [data-testid="stSpinner"] div {{
        color: #14328c;
        font-weight: 600;
        font-size: 0.95rem;
    }}
    @keyframes sw-spin {{
        from {{ transform: rotate(0deg); }}
        to {{ transform: rotate(360deg); }}
    }}
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
        ("hidden_columns", []),
        # --- PPB (Permintaan Pembelian Barang) ---
        ("ppb_df", None),
        ("ppb_file_name", None),
        ("ppb_signature", None),
        ("ppb_debug", None),
        # --- NPBG (Nota Pengeluaran Barang Gudang) ---
        ("npbg_df", None),
        ("npbg_file_name", None),
        ("npbg_signature", None),
        ("npbg_debug", None),
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
    sel_min, sel_max = filters["selisih_range"]
    result = result[(result["Selisih"] >= sel_min) & (result["Selisih"] <= sel_max)]
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
    st.sidebar.header("🔎 Filter Inventory")
    st.sidebar.caption("Berlaku untuk tab Dashboard, Data Inventory, dan Procurement. "
                       "Tab PPB & NPBG punya filter sendiri di dalamnya.")
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

    # Selisih (Sisa Stok - Safety Stock) bisa negatif, jadi tidak dibatasi
    # min_value=0 seperti Lead Time.
    sel_min_data = int(df["Selisih"].min()) if not df.empty else 0
    sel_max_data = int(df["Selisih"].max()) if not df.empty else 0

    st.sidebar.caption("Range Selisih")
    sel_col1, sel_col2 = st.sidebar.columns(2)
    sel_min = sel_col1.number_input("Dari", value=sel_min_data, step=1, key="selisih_filter_min")
    sel_max = sel_col2.number_input("Sampai", value=sel_max_data, step=1, key="selisih_filter_max")
    selisih_range = (sel_min, sel_max)

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

    any_active = bool(
        kategori_induk or kategori_anak1 or kategori_anak2 or kategori_anak3 or uom
        or gudang or status or perlu_blueprint or kode_search or desk_search
        or lead_time_range != (lt_min_data, lt_max_data)
        or selisih_range != (sel_min_data, sel_max_data)
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
        "selisih_range": selisih_range,
        "any_active": any_active,
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


def render_chart(title: str, caption: str, fig, empty_message: str = None):
    """Render one chart inside a bordered card (see the
    `stVerticalBlockBorderWrapper` CSS rule) so the dashboard reads as a grid
    of widgets rather than plots floating loose on the page.
    """
    with st.container(border=True):
        render_chart_header(title, caption)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        elif empty_message:
            st.success(empty_message)


def render_welcome():
    st.markdown(
        """
        <div style="padding: 6px 0 18px 0;">
        <p style="font-size: 1rem; opacity: 0.85; max-width: 720px;">
        Upload Excel inventory, edit langsung di tabel, dan sisanya KPI, chart, insight,
        rekomendasi pembelian auto ikut update sendiri. <b> Gak perlu refresh.</b>
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
    st.caption(
        "Di sidebar ada 3 upload: **Excel Inventory** (data barang/stok), **Excel PPB** "
        "(permintaan pembelian), dan **Excel NPBG** (barang keluar gudang). "
        "Bisa salah satu dulu — PPB & NPBG juga bisa dibuka tanpa data inventory."
    )

    st.markdown("##### Belum punya file? Pakai template ini aja:")
    st.download_button(
        "📥 Download Template Excel",
        data=_cached_template_bytes(),
        file_name="template_stockwise.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="template_download_welcome",
    )
    st.caption(
        "Formatnya udah sesuai, termasuk contoh Sisa Stok kayak \"STOK 15 PCS\" — tinggal isi datanya."
    )


def handle_ppb_upload(uploaded_ppb):
    """Parse an uploaded PPB workbook into session_state (debounced on file signature)."""
    if uploaded_ppb is None:
        return
    signature = f"{uploaded_ppb.name}-{uploaded_ppb.size}"
    if signature == st.session_state.ppb_signature:
        return
    with st.spinner("Membaca file PPB..."):
        ppb_df, error, debug = load_ppb(uploaded_ppb)
    st.session_state.ppb_debug = debug
    if error:
        st.sidebar.error(error)
        return
    st.session_state.ppb_df = ppb_df
    st.session_state.ppb_signature = signature
    st.session_state.ppb_file_name = uploaded_ppb.name
    st.toast(
        f"PPB dimuat: {ppb_df['No PPB'].nunique():,} PPB / {len(ppb_df):,} baris item.", icon="📋"
    )


@st.cache_data(show_spinner=False)
def _cached_ppb_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# ---- Shared helpers for the PPB / NPBG (transaction) tabs ----

_CHART_FONT = dict(family="'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif")


def _txn_bar(mapping: dict, value_title: str, color: str = SERIES_BLUE, height: int = 360, top: int = 10):
    """A horizontal bar figure styled like the Dashboard charts (transparent bg,
    Inter font, blue). `mapping` = {label: value}, drawn biggest-at-top, Top `top`."""
    if not mapping:
        return None
    ser = pd.Series(mapping).sort_values(ascending=False).head(top).sort_values(ascending=True)
    labels = [str(x).replace("(kosong)", "(tanpa nilai)") for x in ser.index]
    fig = px.bar(x=ser.values, y=labels, orientation="h")
    fig.update_traces(marker_color=color, hovertemplate="%{y}: %{x:,.0f}<extra></extra>")
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=6, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=_CHART_FONT,
        xaxis_title=value_title, yaxis_title="",
    )
    fig.update_xaxes(gridcolor="#dde6f4", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return fig


def _txn_month_bar(per_month: dict):
    if not per_month:
        return None
    ser = pd.Series(per_month).sort_index()
    fig = px.bar(x=ser.index, y=ser.values)
    fig.update_traces(marker_color=SERIES_BLUE, hovertemplate="%{x}: %{y:,.0f}<extra></extra>")
    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=_CHART_FONT,
        xaxis_title="", yaxis_title="Kuantitas",
    )
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="#dde6f4", zeroline=False)
    return fig


def _txn_kpi_cards(cards: list):
    """KPI cards in the same style as the Dashboard (`.sw-kpi-*`). `cards` =
    list of (icon, label, value, sub)."""
    html = ['<div class="sw-kpi-grid">']
    for icon, label, value, sub in cards:
        html.append(
            f'<div class="sw-kpi-card">'
            f'<div class="sw-kpi-icon" style="background:{SERIES_BLUE}1a;color:{SERIES_BLUE};">{icon}</div>'
            f'<div class="sw-kpi-body"><div class="sw-kpi-label">{label}</div>'
            f'<div class="sw-kpi-value" style="color:{SERIES_BLUE};">{value}</div>'
            f'<div class="sw-kpi-sub">{sub}</div></div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _txn_empty_state(judul: str, file_hint: str, sheet: str, kolom_kunci: str):
    st.info(f"👈 Upload file **{judul}** dulu di sidebar.")
    st.caption(
        f"File `{file_hint}` — sistem otomatis pakai sheet **{sheet}**, cari baris header "
        f"(yang ada kolom *{kolom_kunci}*), dan buang baris kosong."
    )


def _fmt_period(s: dict) -> str:
    def f(v):
        return v.strftime("%d %b %Y") if v is not None and pd.notna(v) else "-"
    return f"{f(s['date_min'])} – {f(s['date_max'])}"


def render_ppb_view(ppb_df: pd.DataFrame):
    """Tampilan data PPB: KPI, sebaran status/divisi, filter, tabel."""
    if ppb_df is None or ppb_df.empty:
        _txn_empty_state("PPB", "1. PPB - RI.xlsx", "PPB", "No PPB")
        return

    s = ppb_summary(ppb_df)
    n_requested = int((ppb_df["Status"].str.lower() == "requested").sum()) if "Status" in ppb_df.columns else 0

    _txn_kpi_cards([
        ("📋", "Jumlah PPB", f"{s['total_ppb']:,}", "nomor PPB unik"),
        ("🧾", "Baris Item", f"{s['total_item']:,}", "satu baris = satu item diminta"),
        ("📦", "Total Kuantitas", f"{s['total_qty']:,.0f}", "seluruh item yang diminta"),
        ("⏳", "Masih 'Requested'", f"{n_requested:,}", "baris item belum diproses"),
    ])
    st.caption(f"Periode PPB: **{_fmt_period(s)}**.")

    st.divider()
    render_section_header("Sebaran PPB", "Berdasarkan status dan divisi peminta.")
    c1, c2 = st.columns(2)
    with c1:
        render_chart("Status PPB", "Jumlah baris item per status.",
                     _txn_bar(s["per_status"], "Baris item"))
    with c2:
        render_chart("PPB per Divisi (Top 10)", "Divisi peminta terbanyak.",
                     _txn_bar(s["per_divisi"], "Baris item"))

    st.divider()
    render_section_header("Daftar PPB", "Filter dulu, lalu unduh kalau perlu.")

    with st.container(border=True):
        fcol1, fcol2, fcol3 = st.columns([1, 1, 2])
        status_opts = sorted(x for x in ppb_df["Status"].dropna().unique() if str(x).strip())
        divisi_opts = sorted(x for x in ppb_df["Divisi"].dropna().unique() if str(x).strip())
        f_status = fcol1.multiselect("Status", status_opts, key="ppb_f_status", placeholder="Semua status")
        f_divisi = fcol2.multiselect("Divisi", divisi_opts, key="ppb_f_divisi", placeholder="Semua divisi")
        f_search = fcol3.text_input("Cari", key="ppb_f_search",
                                    placeholder="No PPB, deskripsi barang, atau nama peminta…")

        view = ppb_df
        if f_status:
            view = view[view["Status"].isin(f_status)]
        if f_divisi:
            view = view[view["Divisi"].isin(f_divisi)]
        if f_search:
            q = f_search.strip()
            mask = (
                view["No PPB"].astype(str).str.contains(q, case=False, na=False)
                | view["Deskripsi Barang"].astype(str).str.contains(q, case=False, na=False)
                | view["Peminta"].astype(str).str.contains(q, case=False, na=False)
            )
            view = view[mask]

        st.caption(f"Menampilkan **{len(view):,}** dari **{len(ppb_df):,}** baris item — "
                   f"**{view['No PPB'].nunique():,}** PPB.")

        show_cols = [c for c in PPB_DISPLAY_COLUMNS if c in view.columns]
        display = view[show_cols].copy()
        if "Tgl PPB" in display.columns:
            display["Tgl PPB"] = display["Tgl PPB"].dt.strftime("%Y-%m-%d")
        st.dataframe(display, use_container_width=True, hide_index=True, height=430)

        st.download_button(
            "⬇️ Download CSV (sesuai filter)",
            data=_cached_ppb_csv(view[show_cols]),
            file_name="ppb_export.csv", mime="text/csv", key="ppb_csv_download",
        )

    debug = st.session_state.ppb_debug
    if debug:
        with st.expander("🐞 Debug PPB — sheet, header, kolom yang terdeteksi"):
            st.write("Sheet pada workbook:", debug.get("all_sheets"))
            st.write("Sheet yang dipakai:", debug.get("sheet"))
            st.write("Baris header (Excel):", debug.get("header_row"))
            st.write("Kolom terdeteksi:", debug.get("columns"))


def handle_npbg_upload(uploaded_npbg):
    """Parse an uploaded NPBG workbook into session_state (debounced on signature)."""
    if uploaded_npbg is None:
        return
    signature = f"{uploaded_npbg.name}-{uploaded_npbg.size}"
    if signature == st.session_state.npbg_signature:
        return
    with st.spinner("Membaca file NPBG..."):
        npbg_df, error, debug = load_npbg(uploaded_npbg)
    st.session_state.npbg_debug = debug
    if error:
        st.sidebar.error(error)
        return
    st.session_state.npbg_df = npbg_df
    st.session_state.npbg_signature = signature
    st.session_state.npbg_file_name = uploaded_npbg.name
    st.toast(
        f"NPBG dimuat: {npbg_df['No NPBG'].nunique():,} NPBG / {len(npbg_df):,} baris item.", icon="📤"
    )


@st.cache_data(show_spinner=False)
def _cached_npbg_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def render_npbg_view(npbg_df: pd.DataFrame):
    """Tampilan data NPBG (barang keluar): KPI, trend bulanan, sebaran, filter, tabel."""
    if npbg_df is None or npbg_df.empty:
        _txn_empty_state("NPBG", "2. NPBG.xlsx", "NPBG", "No NPBG")
        return

    s = npbg_summary(npbg_df)
    n_months = max(len(s["per_month"]), 1)
    avg_month = s["total_qty"] / n_months
    n_jual = int((npbg_df["Tipe NPBG"].str.upper() == "PENJUALAN").sum()) if "Tipe NPBG" in npbg_df.columns else 0

    _txn_kpi_cards([
        ("📤", "Jumlah NPBG", f"{s['total_npbg']:,}", "nomor NPBG unik"),
        ("🧾", "Baris Item Keluar", f"{s['total_item']:,}", "satu baris = satu item keluar"),
        ("📦", "Total Kuantitas Keluar", f"{s['total_qty']:,.0f}", "seluruh periode"),
        ("📈", "Rata-rata / Bulan", f"{avg_month:,.0f}", f"dari {n_months} bulan aktif"),
    ])
    st.caption(f"Periode NPBG: **{_fmt_period(s)}**  ·  {n_jual:,} baris bertipe PENJUALAN.")

    if s["per_month"]:
        st.divider()
        render_section_header("Barang Keluar per Bulan", "Total kuantitas NPBG tiap bulan — pola pemakaian gudang.")
        render_chart("Kuantitas keluar per bulan", "", _txn_month_bar(s["per_month"]))

    st.divider()
    render_section_header("Sebaran NPBG", "Berdasarkan klasifikasi keperluan dan divisi pemakai.")
    c1, c2 = st.columns(2)
    with c1:
        render_chart("NPBG per Klasifikasi (Top 10)", "Untuk apa barang dikeluarkan.",
                     _txn_bar(s["per_klasifikasi"], "Baris item"))
    with c2:
        render_chart("NPBG per Divisi Pemakai (Top 10)", "Divisi yang paling banyak keluarkan barang.",
                     _txn_bar(s["per_divisi"], "Baris item"))

    st.divider()
    render_section_header("Daftar NPBG", "Filter dulu, lalu unduh kalau perlu.")

    with st.container(border=True):
        fcol1, fcol2, fcol3, fcol4 = st.columns([1, 1, 1, 2])
        klas_opts = sorted(x for x in npbg_df["Klasifikasi"].dropna().unique() if str(x).strip()) if "Klasifikasi" in npbg_df.columns else []
        div_opts = sorted(x for x in npbg_df["Divisi"].dropna().unique() if str(x).strip()) if "Divisi" in npbg_df.columns else []
        tipe_opts = sorted(x for x in npbg_df["Tipe NPBG"].dropna().unique() if str(x).strip()) if "Tipe NPBG" in npbg_df.columns else []
        f_klas = fcol1.multiselect("Klasifikasi", klas_opts, key="npbg_f_klas", placeholder="Semua")
        f_div = fcol2.multiselect("Divisi", div_opts, key="npbg_f_div", placeholder="Semua")
        f_tipe = fcol3.multiselect("Tipe", tipe_opts, key="npbg_f_tipe", placeholder="Semua")
        f_search = fcol4.text_input("Cari", key="npbg_f_search",
                                    placeholder="No NPBG, deskripsi, pelanggan, proyek, atau peminta…")

        view = npbg_df
        if f_klas:
            view = view[view["Klasifikasi"].isin(f_klas)]
        if f_div:
            view = view[view["Divisi"].isin(f_div)]
        if f_tipe:
            view = view[view["Tipe NPBG"].isin(f_tipe)]
        if f_search:
            q = f_search.strip()
            cols_search = [c for c in ["No NPBG", "Deskripsi Barang", "Pelanggan", "Nama Proyek", "Peminta"] if c in view.columns]
            mask = pd.Series(False, index=view.index)
            for c in cols_search:
                mask = mask | view[c].astype(str).str.contains(q, case=False, na=False)
            view = view[mask]

        st.caption(f"Menampilkan **{len(view):,}** dari **{len(npbg_df):,}** baris item — "
                   f"**{view['No NPBG'].nunique():,}** NPBG, total qty **{view['Kuantitas'].sum():,.0f}**.")

        show_cols = [c for c in NPBG_DISPLAY_COLUMNS if c in view.columns]
        display = view[show_cols].copy()
        if "Tgl NPBG" in display.columns:
            display["Tgl NPBG"] = display["Tgl NPBG"].dt.strftime("%Y-%m-%d")
        st.dataframe(display, use_container_width=True, hide_index=True, height=430)

        st.download_button(
            "⬇️ Download CSV (sesuai filter)",
            data=_cached_npbg_csv(view[show_cols]),
            file_name="npbg_export.csv", mime="text/csv", key="npbg_csv_download",
        )

    debug = st.session_state.npbg_debug
    if debug:
        with st.expander("🐞 Debug NPBG — sheet, header, kolom yang terdeteksi"):
            st.write("Sheet pada workbook:", debug.get("all_sheets"))
            st.write("Sheet yang dipakai:", debug.get("sheet"))
            st.write("Baris header (Excel):", debug.get("header_row"))
            st.write("Kolom terdeteksi:", debug.get("columns"))


def render_no_master_view():
    """Kalau master inventory belum diupload tapi PPB/NPBG sudah — tampilkan itu saja."""
    st.info(
        "Data inventory master belum diupload — menampilkan data transaksi saja. "
        "Upload **Excel Inventory** di sidebar untuk dashboard stok lengkap."
    )
    available = []
    if st.session_state.ppb_df is not None:
        available.append((
            "📋 PPB", "Permintaan Pembelian Barang — apa yang diminta untuk dibeli.",
            lambda: render_ppb_view(st.session_state.ppb_df),
        ))
    if st.session_state.npbg_df is not None:
        available.append((
            "📤 NPBG", "Nota Pengeluaran Barang Gudang — barang yang keluar dari gudang.",
            lambda: render_npbg_view(st.session_state.npbg_df),
        ))
    if len(available) == 1:
        label, subtitle, renderer = available[0]
        render_section_header(label, subtitle)
        renderer()
    else:
        for tab, (label, subtitle, renderer) in zip(st.tabs([lbl for lbl, _, _ in available]), available):
            with tab:
                render_section_header(label, subtitle)
                renderer()


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
    st.sidebar.header("📤 Upload Data")
    st.sidebar.caption("Upload salah satu atau semuanya — tiap file berdiri sendiri.")

    uploaded = st.sidebar.file_uploader(
        "1. Excel Inventory", type=["xlsx", "xls"],
        help="Data master barang & stok. Membuka tab Dashboard, Data Inventory, Procurement, Export.",
    )
    if st.session_state.df is not None:
        st.sidebar.caption(f"✅ **{st.session_state.file_name}** — {len(st.session_state.df):,} barang")
    else:
        st.sidebar.download_button(
            "📥 Belum punya? Download template",
            data=_cached_template_bytes(),
            file_name="template_stockwise.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="template_download_sidebar",
        )

    uploaded_ppb = st.sidebar.file_uploader(
        "2. Excel PPB", type=["xlsx", "xls"], key="ppb_uploader",
        help="Permintaan Pembelian Barang (mis. `1. PPB - RI.xlsx`). Membuka tab 📋 PPB.",
    )
    handle_ppb_upload(uploaded_ppb)
    if st.session_state.ppb_df is not None:
        st.sidebar.caption(
            f"✅ **{st.session_state.ppb_file_name}** — {st.session_state.ppb_df['No PPB'].nunique():,} PPB"
        )

    uploaded_npbg = st.sidebar.file_uploader(
        "3. Excel NPBG", type=["xlsx", "xls"], key="npbg_uploader",
        help="Nota Pengeluaran Barang Gudang (mis. `2. NPBG.xlsx`) — barang keluar. Membuka tab 📤 NPBG.",
    )
    handle_npbg_upload(uploaded_npbg)
    if st.session_state.npbg_df is not None:
        st.sidebar.caption(
            f"✅ **{st.session_state.npbg_file_name}** — {st.session_state.npbg_df['No NPBG'].nunique():,} NPBG"
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
            # A new file may not have the same columns as the last one — reset
            # column visibility so a stale hidden-column name can't crash the
            # "Kelola Kolom" multiselect (it errors if its value contains an
            # option that no longer exists).
            st.session_state.hidden_columns = []
            st.session_state.pop("hidden_columns_picker", None)
            st.toast(f"Berhasil memuat {len(df):,} barang dari '{uploaded.name}'.", icon="✅")

    if st.session_state.df is None:
        if st.session_state.ppb_df is not None or st.session_state.npbg_df is not None:
            render_no_master_view()
            st.stop()
        render_welcome()
        st.stop()

    full_df = st.session_state.df
    st.sidebar.divider()

    filters = render_sidebar(full_df)
    filtered_view = apply_filters(full_df, filters)

    tab1, tab2, tab3, tab5, tab6, tab4 = st.tabs(
        ["📊 Dashboard", "🗂️ Data Inventory", "🚚 Procurement", "📋 PPB", "📤 NPBG", "⬇️ Export"]
    )

    with tab2:
        render_section_header(
            "Data Inventory",
            "Edit langsung di tabel — Selisih, Status, Defisit, Priority, dan Rekomendasi ikut kehitung ulang.",
        )
        n_tidak_aman = int((filtered_view["Status"] == STATUS_TIDAK_AMAN).sum())
        col_caption, col_menu = st.columns([6, 1])
        with col_caption:
            st.caption(
                f"Nampilin **{len(filtered_view):,}** dari **{len(full_df):,}** barang sesuai filter "
                f"— **{n_tidak_aman:,}** di antaranya TIDAK AMAN."
            )
        with col_menu:
            with st.popover("⋮", use_container_width=True, help="Kelola kolom — sembunyikan/hapus dari tampilan & download"):
                st.markdown("**Kelola Kolom**")
                st.caption(
                    "Kolom yang disembunyikan juga ikut hilang dari download Excel & CSV "
                    "(laporan PDF tetap menampilkan semua kolom yang dibutuhkan ringkasannya)."
                )
                hidden_selection = st.multiselect(
                    "Sembunyikan kolom",
                    options=list(filtered_view.columns),
                    default=[c for c in st.session_state.hidden_columns if c in filtered_view.columns],
                    key="hidden_columns_picker",
                )
                st.session_state.hidden_columns = hidden_selection
                if hidden_selection and st.button("↺ Tampilkan semua kolom", use_container_width=True):
                    st.session_state.hidden_columns = []
                    st.rerun()

        debug_info = st.session_state.debug_info
        if debug_info:
            with st.expander("🐞 Debug Excel"):
                st.write("Sheet terdeteksi pada workbook:", debug_info.get("all_sheets"))
                st.write("Sheet yang digunakan:", debug_info.get("sheet"))
                st.write("Baris header:", debug_info.get("header_row"))
                st.write("Kolom terdeteksi:", debug_info.get("columns"))
                st.write("Pilihan dropdown dari sheet 'Dropdown List':", st.session_state.dropdown_options or "(tidak ditemukan)")

        visible_cols = [c for c in filtered_view.columns if c not in st.session_state.hidden_columns]
        editor_key = (
            f"inventory_editor::{filter_signature(filters)}::hide={','.join(sorted(st.session_state.hidden_columns))}"
        )
        edited_view = render_data_editor(
            filtered_view[visible_cols],
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
            render_chart("Status Inventory", "Proporsi barang AMAN vs TIDAK AMAN.", status_donut(filtered_final))
        with c2:
            render_chart(
                "Top Barang dengan Defisit Terbesar",
                "Barang paling kurang dari safety stock-nya.",
                top_deficit_bar(filtered_final),
                empty_message="✅ Tidak ada barang dengan defisit stok.",
            )

        render_chart(
            "Stok vs Safety Stock",
            "Perbandingan langsung: stok saat ini vs batas amannya.",
            stock_vs_safety_bar(filtered_final),
        )

        st.divider()
        render_section_header("📍 Analisis per Lokasi & Kategori", "Di gudang atau kategori mana masalah paling banyak.")
        c3, c4 = st.columns(2)
        with c3:
            render_chart(
                "Inventory per Gudang — Status",
                "Jumlah barang aman/tidak aman di tiap gudang.",
                warehouse_status_bar(filtered_final),
            )
            render_chart(
                "Inventory per Gudang — Stok vs Safety Stock",
                "Total stok vs total safety stock per gudang.",
                warehouse_stock_bar(filtered_final),
            )
        with c4:
            render_chart(
                "Inventory per Kategori Induk",
                "Jumlah barang aman/tidak aman per kategori.",
                category_status_bar(filtered_final),
            )
            render_chart(
                "Lead Time vs Defisit",
                "Barang lead time tinggi + defisit besar = prioritas procurement.",
                lead_time_scatter(filtered_final),
            )

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
            priority_row_tint = {"HIGH": f"{COLOR_TIDAK_AMAN}12", "MEDIUM": f"{COLOR_WARNING}0f"}

            def _style_priority(val):
                color = priority_colors.get(val)
                return f"background-color:{color}26; color:{color}; font-weight:700;" if color else ""

            def _tint_row(row):
                # Light background wash across the whole row so the most urgent
                # items are easy to spot at a glance, not just the Priority
                # Level cell — the cell itself still gets the stronger, bolded
                # color from _style_priority (applied after, so it wins there).
                bg = priority_row_tint.get(row.get("Priority Level"), "")
                style = f"background-color:{bg};" if bg else ""
                return [style] * len(row)

            # Without an explicit format, pandas Styler prints floats at full
            # precision (e.g. "50.000000" instead of "50") — these columns are
            # always whole numbers, so round the display to 0 decimals.
            number_cols = [c for c in ["Safety Stock", "Sisa Stok", "Defisit", "Lead Time", "Priority Score"] if c in cols]
            styled = (
                unsafe[cols]
                .style.format({c: "{:,.0f}" for c in number_cols})
                .apply(_tint_row, axis=1)
                .map(_style_priority, subset=["Priority Level"])
            )
            with st.container(border=True):
                st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab5:
        render_section_header(
            "PPB — Permintaan Pembelian Barang",
            "Upload file PPB di sidebar untuk melihat daftar permintaan pembelian.",
        )
        render_ppb_view(st.session_state.ppb_df)

    with tab6:
        render_section_header(
            "NPBG — Nota Pengeluaran Barang Gudang",
            "Upload file NPBG di sidebar untuk melihat riwayat barang keluar gudang.",
        )
        render_npbg_view(st.session_state.npbg_df)

    with tab4:
        render_section_header(
            "Export Data",
            "Hasil export sudah mencakup Selisih, Status, Defisit, Priority Score/Level, dan Rekomendasi.",
        )

        scope_options = ["Seluruh Data", "Data Terfilter"]
        default_scope_idx = 1 if filters.get("any_active") else 0
        export_scope = st.radio("Data yang diexport", scope_options, index=default_scope_idx, horizontal=True)
        # Row-filtered dataset — this is what the PDF report uses. Its KPI
        # summary reads core columns (Status, Sisa Stok, Safety Stock, Defisit,
        # Priority Score) directly, so it always gets every column intact even
        # when some are hidden from the editor/Excel/CSV below.
        export_rows_df = full_df if export_scope == "Seluruh Data" else filtered_final

        # Excel/CSV mirror whatever the user is actually looking at, so hidden
        # columns are dropped from those two (but not the PDF — see above).
        export_df = export_rows_df
        if st.session_state.hidden_columns:
            visible_export_cols = [c for c in export_df.columns if c not in st.session_state.hidden_columns]
            export_df = export_df[visible_export_cols]

        scope_caption = f"Akan mengekspor **{len(export_df):,}** baris"
        if st.session_state.hidden_columns:
            scope_caption += (
                f", **{len(st.session_state.hidden_columns)}** kolom disembunyikan dari Excel/CSV "
                "(laporan PDF tetap lengkap)"
            )
        st.caption(scope_caption + ".")

        st.write("")
        col1, col2, col3 = st.columns(3)
        with col1, st.container(border=True):
            st.markdown(
                '<div class="sw-welcome-feature" style="border:none;box-shadow:none;padding:0;">'
                '<span class="emoji">📊</span><b>Excel</b>'
                '<p>Data lengkap semua kolom — buat diedit atau diolah lagi.</p></div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇️ Download Excel",
                data=_cached_excel_bytes(export_df),
                file_name="stockwise_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col2, st.container(border=True):
            st.markdown(
                '<div class="sw-welcome-feature" style="border:none;box-shadow:none;padding:0;">'
                '<span class="emoji">🖨️</span><b>PDF</b>'
                '<p>Laporan siap cetak — ringkasan KPI, daftar barang, Procurement Priority.</p></div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇️ Download PDF",
                data=_cached_pdf_bytes(export_rows_df, export_scope, st.session_state.file_name or ""),
                file_name="stockwise_laporan.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with col3, st.container(border=True):
            st.markdown(
                '<div class="sw-welcome-feature" style="border:none;box-shadow:none;padding:0;">'
                '<span class="emoji">📄</span><b>CSV</b>'
                '<p>Format ringan buat diimpor ke sistem atau tool lain.</p></div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇️ Download CSV",
                data=_cached_csv_bytes(export_df),
                file_name="stockwise_export.csv",
                mime="text/csv",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
