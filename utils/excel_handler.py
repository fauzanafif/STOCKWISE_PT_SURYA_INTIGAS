"""Excel ingest/export: column normalization, numeric parsing, validation."""
import io
import re

import pandas as pd

# Canonical column names, in the order they appear in the source Excel.
CANONICAL_COLUMNS = [
    "Kode Barang",
    "Kategori Induk",
    "Kategori Anak 1",
    "Kategori Anak 2",
    "Kategori Anak 3",
    "Deskripsi Barang",
    "UoM",
    "Perlu Blueprint?",
    "Nama Alias",
    "Letak Gudang",
    "Letak Rak",
    "Blueprint IMG",
    "Blueprint Detail PDF",
    "Blueprint 3D View",
    "Safety Stock",
    "Sisa Stok",
    "Lead Time",
]

# Columns that must exist (or be derivable) for the app to function.
REQUIRED_COLUMNS = [
    "Kode Barang",
    "Deskripsi Barang",
    "Safety Stock",
    "Sisa Stok",
]

NUMERIC_COLUMNS = ["Safety Stock", "Sisa Stok", "Lead Time"]

EDITABLE_COLUMNS = [
    "Kode Barang",
    "Kategori Induk",
    "Kategori Anak 1",
    "Kategori Anak 2",
    "Kategori Anak 3",
    "Deskripsi Barang",
    "UoM",
    "Perlu Blueprint?",
    "Nama Alias",
    "Letak Gudang",
    "Letak Rak",
    "Safety Stock",
    "Sisa Stok",
    "Lead Time",
]

CALCULATED_COLUMNS = [
    "Selisih",
    "Status",
    "Defisit",
    "Priority Score",
    "Priority Level",
    "Rekomendasi",
]

REFERENCE_COLUMNS = ["Blueprint IMG", "Blueprint Detail PDF", "Blueprint 3D View"]

_NUMBER_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)?")


def _normalize_header(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to their canonical form, matching case/whitespace-insensitively."""
    lookup = {_normalize_header(c): c for c in CANONICAL_COLUMNS}
    rename_map = {}
    for col in df.columns:
        key = _normalize_header(col)
        if key in lookup:
            rename_map[col] = lookup[key]
    return df.rename(columns=rename_map)


def validate_columns(df: pd.DataFrame) -> list:
    """Return the list of required columns missing from df (empty if all present)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def extract_number(value) -> float:
    """Pull a numeric value out of strings like 'STOK 15 PCS' -> 15.0.

    Handles plain numbers, None/NaN, and empty strings safely (returns 0.0).
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return 0.0
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    match = _NUMBER_PATTERN.search(text.replace(",", "."))
    if not match:
        return 0.0
    try:
        return float(match.group())
    except ValueError:
        return 0.0


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add any missing optional canonical columns as empty, in canonical order."""
    df = df.copy()
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col not in NUMERIC_COLUMNS else 0
    ordered = CANONICAL_COLUMNS + [c for c in df.columns if c not in CANONICAL_COLUMNS]
    df = df[ordered]

    text_cols = [c for c in CANONICAL_COLUMNS if c not in NUMERIC_COLUMNS]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace("nan", "")
    return df


def load_excel(uploaded_file):
    """Read an uploaded Excel file into a DataFrame.

    Returns (df, error_message). df is None if reading failed.
    """
    try:
        raw = pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        return None, f"Gagal membaca file Excel: {exc}"

    df = normalize_columns(raw)
    missing = validate_columns(df)
    if missing:
        cols = ", ".join(f"`{c}`" for c in missing)
        return None, f"Kolom wajib tidak ditemukan pada file Excel: {cols}."

    df = ensure_columns(df)

    for col in NUMERIC_COLUMNS:
        df[col] = df[col].apply(extract_number)

    df = df.reset_index(drop=True)
    return df, None


def to_export_bytes(df: pd.DataFrame) -> bytes:
    """Build a formatted .xlsx file (colored Status column) and return its bytes."""
    export_df = df.copy()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Inventory")
        workbook = writer.book
        worksheet = writer.sheets["Inventory"]

        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#1F2937", "font_color": "#FFFFFF", "border": 1}
        )
        for col_idx, col_name in enumerate(export_df.columns):
            worksheet.write(0, col_idx, col_name, header_fmt)
            width = max(12, min(40, len(str(col_name)) + 4))
            worksheet.set_column(col_idx, col_idx, width)

        if "Status" in export_df.columns:
            status_col = export_df.columns.get_loc("Status")
            n_rows = len(export_df)
            aman_fmt = workbook.add_format({"bg_color": "#D1FAE5", "font_color": "#065F46"})
            tidak_aman_fmt = workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"})
            worksheet.conditional_format(
                1, status_col, n_rows, status_col,
                {"type": "cell", "criteria": "equal to", "value": '"TIDAK AMAN"', "format": tidak_aman_fmt},
            )
            worksheet.conditional_format(
                1, status_col, n_rows, status_col,
                {"type": "cell", "criteria": "equal to", "value": '"AMAN"', "format": aman_fmt},
            )

    return buffer.getvalue()
