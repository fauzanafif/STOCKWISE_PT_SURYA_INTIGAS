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

CALCULATED_COLUMNS = [
    "Selisih",
    "Status",
    "Defisit",
    "Priority Score",
    "Priority Level",
    "Rekomendasi",
]

REFERENCE_COLUMNS = ["Blueprint IMG", "Blueprint Detail PDF", "Blueprint 3D View"]

# Keyword sets used to fuzzy-match a canonical column when the source header
# isn't an exact match (e.g. "SISA STOK (22/08/2026)" instead of "Sisa Stok").
# Every keyword must appear (as a substring) in the source header, checked in
# this order so more specific targets (e.g. "Letak Rak") don't get stolen by
# a looser one matched earlier.
CANONICAL_KEYWORDS = {
    "Kode Barang": ["KODE", "BARANG"],
    "Deskripsi Barang": ["DESKRIPSI"],
    "Safety Stock": ["SAFETY", "STOCK"],
    "Sisa Stok": ["SISA", "STOK"],
    "Lead Time": ["LEAD", "TIME"],
    "Kategori Induk": ["KATEGORI", "INDUK"],
    "Kategori Anak 1": ["KATEGORI", "ANAK", "1"],
    "Kategori Anak 2": ["KATEGORI", "ANAK", "2"],
    "Kategori Anak 3": ["KATEGORI", "ANAK", "3"],
    "UoM": ["UOM"],
    "Perlu Blueprint?": ["PERLU", "BLUEPRINT"],
    "Nama Alias": ["ALIAS"],
    "Letak Gudang": ["LETAK", "GUDANG"],
    "Letak Rak": ["LETAK", "RAK"],
    "Blueprint IMG": ["BLUEPRINT", "IMG"],
    "Blueprint Detail PDF": ["BLUEPRINT", "DETAIL"],
    "Blueprint 3D View": ["BLUEPRINT", "3D"],
}

MAX_HEADER_SCAN_ROWS = 50

_NUMBER_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)?")


def _normalize_header(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def find_column(df: pd.DataFrame, keywords: list, exclude: set = frozenset()):
    """Return the first column whose header contains every keyword (order preserved)."""
    for col in df.columns:
        if col in exclude:
            continue
        col_upper = str(col).strip().upper()
        if all(str(kw).upper() in col_upper for kw in keywords):
            return col
    return None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to their canonical form, matching case/whitespace-insensitively."""
    lookup = {_normalize_header(c): c for c in CANONICAL_COLUMNS}
    rename_map = {}
    for col in df.columns:
        key = _normalize_header(col)
        if key in lookup:
            rename_map[col] = lookup[key]
    return df.rename(columns=rename_map)


def fuzzy_match_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Catch headers that vary slightly from the canonical name (extra words,
    dates, punctuation) via keyword matching, e.g. 'SISA STOK (22/08/2026)' ->
    'Sisa Stok'. Only applied to columns not already renamed by an exact match.
    """
    df = df.copy()
    claimed = {c for c in df.columns if c in CANONICAL_COLUMNS}
    rename_map = {}
    for canonical, keywords in CANONICAL_KEYWORDS.items():
        if canonical in df.columns:
            continue
        match = find_column(df, keywords, exclude=claimed)
        if match is not None:
            rename_map[match] = canonical
            claimed.add(match)
    return df.rename(columns=rename_map)


def detect_header_row(uploaded_file, max_scan_rows: int = MAX_HEADER_SCAN_ROWS):
    """Find the row index (0-based) that holds the real header, by scanning
    the first few rows for a cell containing both "kode" and "barang" (e.g.
    "Kode Barang", "Kode Barang:", "1. Kode Barang" all match). Substring
    matching — rather than requiring the cell to equal "kode barang" exactly —
    tolerates numbering, punctuation, or stray whitespace around the header
    text. Returns None if no such row is found within the scan window.
    """
    uploaded_file.seek(0)
    preview = pd.read_excel(uploaded_file, header=None, nrows=max_scan_rows, engine="openpyxl")
    for idx in range(len(preview)):
        row_values = [_normalize_header(v) for v in preview.iloc[idx].tolist()]
        if any("kode" in v and "barang" in v for v in row_values):
            return idx
    return None


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

    The header row doesn't have to be row 1 — some exports have a title and
    blank rows above it (e.g. "Database Gudang ..." followed by empty rows),
    so the real header row is located by scanning for a "Kode Barang" cell.

    Returns (df, error_message). df is None if reading failed.
    """
    try:
        header_row = detect_header_row(uploaded_file)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        return None, f"Gagal membaca file Excel: {exc}"

    if header_row is None:
        return None, (
            f"Baris header tidak ditemukan (mencari kolom 'Kode Barang' pada "
            f"{MAX_HEADER_SCAN_ROWS} baris pertama file Excel)."
        )

    try:
        uploaded_file.seek(0)
        raw = pd.read_excel(uploaded_file, header=header_row, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        return None, f"Gagal membaca file Excel: {exc}"

    df = normalize_columns(raw)
    df = fuzzy_match_columns(df)
    missing = validate_columns(df)
    if missing:
        cols = ", ".join(f"`{c}`" for c in missing)
        detected = ", ".join(f"`{c}`" for c in df.columns)
        return None, (
            f"Kolom wajib tidak ditemukan pada file Excel: {cols}.\n\n"
            f"Header dibaca dari baris ke-{header_row + 1} pada file, dengan kolom "
            f"yang terdeteksi: {detected}."
        )

    df = ensure_columns(df)

    for col in NUMERIC_COLUMNS:
        df[col] = df[col].apply(extract_number)

    df = df.reset_index(drop=True)
    return df, None


TEMPLATE_TITLE = "Database Gudang STOCKWISE"
TEMPLATE_NOTE = (
    "Isi data mulai baris di bawah header. Baris judul/catatan di atas ini boleh "
    "diubah atau dikosongkan — aplikasi otomatis mencari baris header (baris yang "
    "memuat 'Kode Barang')."
)
TEMPLATE_HEADER_ROW = 4  # 0-indexed -> Excel row 5, matching the real STOCKWISE export layout

TEMPLATE_EXAMPLE_ROWS = [
    {
        "Kode Barang": "PUI.0019",
        "Kategori Induk": "Post-Use Items",
        "Kategori Anak 1": "NEED ASSESSMENT (BEKAS)",
        "Kategori Anak 2": "",
        "Kategori Anak 3": "",
        "Deskripsi Barang": "(BEKAS) ACCU - ASPIRA / 145G51L - N150L / 150Ah 12V",
        "UoM": "PCS",
        "Perlu Blueprint?": "TIDAK",
        "Nama Alias": "",
        "Letak Gudang": "GUDANG 4",
        "Letak Rak": "R1-A1",
        "Blueprint IMG": "",
        "Blueprint Detail PDF": "",
        "Blueprint 3D View": "",
        "Safety Stock": 10,
        "Sisa Stok": "STOK 15 PCS",
        "Lead Time": 5,
    },
    {
        "Kode Barang": "PUI.0020",
        "Kategori Induk": "Post-Use Items",
        "Kategori Anak 1": "NEED ASSESSMENT (BEKAS)",
        "Kategori Anak 2": "",
        "Kategori Anak 3": "",
        "Deskripsi Barang": "(BEKAS) DINAMO STARTER - TOYOTA AVANZA",
        "UoM": "PCS",
        "Perlu Blueprint?": "TIDAK",
        "Nama Alias": "",
        "Letak Gudang": "GUDANG 2",
        "Letak Rak": "R2-B3",
        "Blueprint IMG": "",
        "Blueprint Detail PDF": "",
        "Blueprint 3D View": "",
        "Safety Stock": 10,
        "Sisa Stok": "STOK 0 PCS",
        "Lead Time": 21,
    },
]


def build_template_bytes() -> bytes:
    """Build a downloadable blank Excel template with the expected columns,
    the same title-rows-then-header layout as a real STOCKWISE export, and a
    couple of example rows (one AMAN, one TIDAK AMAN) to illustrate the
    expected format — especially that 'Sisa Stok' accepts text like
    'STOK 15 PCS'.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet("Inventory")
        writer.sheets["Inventory"] = worksheet

        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        note_fmt = workbook.add_format({"italic": True, "font_color": "#898781", "text_wrap": True})
        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#1F2937", "font_color": "#FFFFFF", "border": 1}
        )
        example_fmt = workbook.add_format({"font_color": "#52514e", "italic": True})

        worksheet.write(0, 0, TEMPLATE_TITLE, title_fmt)
        worksheet.merge_range(1, 0, 2, len(CANONICAL_COLUMNS) - 1, TEMPLATE_NOTE, note_fmt)

        for col_idx, col_name in enumerate(CANONICAL_COLUMNS):
            worksheet.write(TEMPLATE_HEADER_ROW, col_idx, col_name, header_fmt)
            width = max(14, min(42, len(col_name) + 6))
            worksheet.set_column(col_idx, col_idx, width)

        for r, example in enumerate(TEMPLATE_EXAMPLE_ROWS, start=TEMPLATE_HEADER_ROW + 1):
            for col_idx, col_name in enumerate(CANONICAL_COLUMNS):
                worksheet.write(r, col_idx, example.get(col_name, ""), example_fmt)

        worksheet.freeze_panes(TEMPLATE_HEADER_ROW + 1, 0)

    return buffer.getvalue()


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

        if "Status" in export_df.columns and len(export_df) > 0:
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
