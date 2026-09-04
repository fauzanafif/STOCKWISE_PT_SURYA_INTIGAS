"""The interactive, editable inventory table (st.data_editor)."""
import streamlit as st

from utils.excel_handler import REFERENCE_COLUMNS


def _options(df, col, extra_options=None):
    """Unique non-blank values for a selectbox, unioned with any extra choices
    (e.g. from the workbook's "Dropdown List" sheet) and always including a
    blank choice so existing empty cells remain a valid (editable) selection.
    """
    values = set()
    if col in df.columns:
        values |= {str(v).strip() for v in df[col].dropna() if str(v).strip()}
    if extra_options:
        values |= {str(v).strip() for v in extra_options.get(col, []) if str(v).strip()}
    return [""] + sorted(values)


def build_column_config(df, extra_options=None):
    config = {
        "Kode Barang": st.column_config.TextColumn("Kode Barang", required=True, width="small"),
        "Kategori Induk": st.column_config.SelectboxColumn(
            "Kategori Induk", options=_options(df, "Kategori Induk", extra_options), width="medium"
        ),
        "Kategori Anak 1": st.column_config.SelectboxColumn(
            "Kategori Anak 1", options=_options(df, "Kategori Anak 1", extra_options), width="medium"
        ),
        "Kategori Anak 2": st.column_config.SelectboxColumn(
            "Kategori Anak 2", options=_options(df, "Kategori Anak 2", extra_options), width="medium"
        ),
        "Kategori Anak 3": st.column_config.SelectboxColumn(
            "Kategori Anak 3", options=_options(df, "Kategori Anak 3", extra_options), width="medium"
        ),
        "Deskripsi Barang": st.column_config.TextColumn("Deskripsi Barang", width="large"),
        "UoM": st.column_config.SelectboxColumn("UoM", options=_options(df, "UoM", extra_options), width="small"),
        "Perlu Blueprint?": st.column_config.SelectboxColumn(
            "Perlu Blueprint?",
            options=sorted(set(_options(df, "Perlu Blueprint?")) | {"YA", "TIDAK"}),
            width="small",
        ),
        "Nama Alias": st.column_config.TextColumn("Nama Alias", width="medium"),
        "Letak Gudang": st.column_config.SelectboxColumn(
            "Letak Gudang", options=_options(df, "Letak Gudang"), width="medium"
        ),
        "Letak Rak": st.column_config.TextColumn("Letak Rak", width="small"),
        "Sisa Stok": st.column_config.NumberColumn("Sisa Stok", min_value=0, step=1, width="small"),
        "Lead Time": st.column_config.NumberColumn("Lead Time", min_value=0, step=1, width="small"),
        "√LT": st.column_config.TextColumn("√LT", width="small"),
        "Safety Stock": st.column_config.NumberColumn("Safety Stock", min_value=0, step=1, width="small"),
        "MIN PR": st.column_config.NumberColumn("MIN PR", min_value=0, step=1, width="small"),
        "Selisih": st.column_config.NumberColumn("Selisih", disabled=True, width="small"),
        "Status": st.column_config.TextColumn("Status", disabled=True, width="small"),
        "Defisit": st.column_config.NumberColumn("Defisit", disabled=True, width="small"),
        "Priority Score": st.column_config.NumberColumn("Priority Score", disabled=True, width="small"),
        "Priority Level": st.column_config.TextColumn("Priority Level", disabled=True, width="small"),
        "Rekomendasi": st.column_config.TextColumn("Rekomendasi", disabled=True, width="large"),
        "NPBG": st.column_config.NumberColumn(
            "NPBG",
            help="Jumlah baris NPBG untuk barang ini (dicocokkan dari file NPBG "
            "berdasarkan Deskripsi Barang). Kosong = tidak ada pasangan / bukan status AMAN.",
            format="%d",
            disabled=True,
            width="small",
        ),
    }
    for col in REFERENCE_COLUMNS:
        config[col] = st.column_config.TextColumn(col, disabled=True, width="medium")
    return config



def render_data_editor(df, options_df=None, extra_options=None, key="inventory_editor"):
    """Render the editable table and return the edited (possibly reshaped) DataFrame.

    `options_df` (defaults to df) supplies the selectbox choices derived from
    the active dataset, so that an active filter doesn't hide valid category
    options that exist elsewhere in the full dataset. `extra_options` adds
    further choices on top (e.g. from the workbook's "Dropdown List" sheet).
    """
    edited = st.data_editor(
        df,
        column_config=build_column_config(options_df if options_df is not None else df, extra_options),
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key=key,
    )
    return edited
