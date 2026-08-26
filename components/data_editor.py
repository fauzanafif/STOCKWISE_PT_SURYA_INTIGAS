"""The interactive, editable inventory table (st.data_editor)."""
import streamlit as st

from utils.excel_handler import REFERENCE_COLUMNS


def _options(df, col):
    """Unique non-blank values for a selectbox, always including a blank choice
    so existing empty cells remain a valid (editable) selection."""
    if col not in df.columns:
        return [""]
    values = sorted({str(v).strip() for v in df[col].dropna() if str(v).strip()})
    return [""] + values


def build_column_config(df):
    config = {
        "Kode Barang": st.column_config.TextColumn("Kode Barang", required=True, width="small"),
        "Kategori Induk": st.column_config.SelectboxColumn(
            "Kategori Induk", options=_options(df, "Kategori Induk"), width="medium"
        ),
        "Kategori Anak 1": st.column_config.SelectboxColumn(
            "Kategori Anak 1", options=_options(df, "Kategori Anak 1"), width="medium"
        ),
        "Kategori Anak 2": st.column_config.SelectboxColumn(
            "Kategori Anak 2", options=_options(df, "Kategori Anak 2"), width="medium"
        ),
        "Kategori Anak 3": st.column_config.SelectboxColumn(
            "Kategori Anak 3", options=_options(df, "Kategori Anak 3"), width="medium"
        ),
        "Deskripsi Barang": st.column_config.TextColumn("Deskripsi Barang", width="large"),
        "UoM": st.column_config.SelectboxColumn("UoM", options=_options(df, "UoM"), width="small"),
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
        "Safety Stock": st.column_config.NumberColumn("Safety Stock", min_value=0, step=1, width="small"),
        "Sisa Stok": st.column_config.NumberColumn("Sisa Stok", min_value=0, step=1, width="small"),
        "Lead Time": st.column_config.NumberColumn("Lead Time", min_value=0, step=1, width="small"),
        "Selisih": st.column_config.NumberColumn("Selisih", disabled=True, width="small"),
        "Status": st.column_config.TextColumn("Status", disabled=True, width="small"),
        "Defisit": st.column_config.NumberColumn("Defisit", disabled=True, width="small"),
        "Priority Score": st.column_config.NumberColumn("Priority Score", disabled=True, width="small"),
        "Priority Level": st.column_config.TextColumn("Priority Level", disabled=True, width="small"),
        "Rekomendasi": st.column_config.TextColumn("Rekomendasi", disabled=True, width="large"),
    }
    for col in REFERENCE_COLUMNS:
        config[col] = st.column_config.TextColumn(col, disabled=True, width="medium")
    return config


def render_data_editor(df, options_df=None, key="inventory_editor"):
    """Render the editable table and return the edited (possibly reshaped) DataFrame.

    `options_df` (defaults to df) supplies the selectbox choices, so that an
    active filter doesn't hide valid category options that exist elsewhere
    in the full dataset.
    """
    edited = st.data_editor(
        df,
        column_config=build_column_config(options_df if options_df is not None else df),
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key=key,
    )
    return edited
