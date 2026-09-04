"""Baca workbook PPB (mis. `1. PPB - RI.xlsx`), sheet **PPB**.

Sama gaya dengan `utils/excel_handler.py`: kembalikan `(df, error, debug_info)`,
deteksi sheet & baris header sendiri, tidak pernah menebak struktur.

Struktur sheet PPB (dari audit file asli):
  kolom A kosong · header di baris ke-3 · kolom:
  No | Tgl PPB | No PPB | Deskripsi Barang | Kuantitas | Satuan | Peminta |
  Divisi | Keterangan | Status | cntRI | sumRI | cntAmend | cntClose | Concat
Satu No PPB bisa punya banyak baris (satu baris per item).
"""
from __future__ import annotations

import re

import pandas as pd

# Kolom yang ditampilkan / dipakai (urut sesuai sumber).
PPB_DISPLAY_COLUMNS = [
    "Tgl PPB", "No PPB", "Deskripsi Barang", "Kuantitas", "Satuan",
    "Peminta", "Divisi", "Status", "Keterangan",
]
# Kolom bantu/rollup di sumber — disimpan tapi tidak ditonjolkan.
PPB_HELPER_COLUMNS = ["No", "cntRI", "sumRI", "cntAmend", "cntClose", "Concat"]

REQUIRED_PPB_COLUMNS = ["No PPB", "Deskripsi Barang"]
PPB_NUMERIC_COLUMNS = ["Kuantitas"]
PPB_DATE_COLUMNS = ["Tgl PPB"]

MAX_HEADER_SCAN_ROWS = 15

# Variasi nama kolom yang diterima → nama kanonik.
_CANON = {
    "No PPB": ["no ppb", "nomor ppb", "no. ppb"],
    "Tgl PPB": ["tgl ppb", "tanggal ppb", "tgl. ppb"],
    "Deskripsi Barang": ["deskripsi barang", "deskripsi", "nama barang"],
    "Kuantitas": ["kuantitas", "qty", "kuantiti", "jumlah"],
    "Satuan": ["satuan", "uom"],
    "Peminta": ["peminta"],
    "Divisi": ["divisi", "departemen", "bagian"],
    "Keterangan": ["keterangan", "catatan"],
    "Status": ["status"],
    "cntRI": ["cntri"],
    "sumRI": ["sumri"],
    "cntAmend": ["cntamend"],
    "cntClose": ["cntclose"],
    "Concat": ["concat"],
    "No": ["no", "no."],
}

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _norm(name) -> str:
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def _to_number(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUMBER_RE.search(str(value).replace(",", "."))
    try:
        return float(m.group()) if m else 0.0
    except (ValueError, AttributeError):
        return 0.0


def select_ppb_sheet(uploaded_file):
    """Pilih sheet PPB: persis bernama 'PPB', lalu sheet yang namanya mengandung
    'ppb' (tapi bukan 'ppb perubahan'), lalu sheet pertama. Return (nama, semua)."""
    uploaded_file.seek(0)
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = xls.sheet_names

    for name in sheets:
        if _norm(name) == "ppb":
            return name, sheets
    for name in sheets:
        n = _norm(name)
        if "ppb" in n and "perubahan" not in n and n != "dropdown list":
            return name, sheets
    return sheets[0], sheets


def detect_ppb_header_row(uploaded_file, sheet_name, max_scan_rows: int = MAX_HEADER_SCAN_ROWS):
    """Cari baris (0-based) yang memuat sel 'No PPB'."""
    uploaded_file.seek(0)
    preview = pd.read_excel(
        uploaded_file, sheet_name=sheet_name, header=None, nrows=max_scan_rows, engine="openpyxl"
    )
    for idx in range(len(preview)):
        row_values = [_norm(v) for v in preview.iloc[idx].tolist()]
        if any(("no ppb" in v or "nomor ppb" in v) for v in row_values):
            return idx
    return None


def normalize_ppb_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {}
    for canon, variants in _CANON.items():
        for v in variants:
            lookup[v] = canon
    rename = {}
    for col in df.columns:
        key = _norm(col)
        if key in lookup:
            rename[col] = lookup[key]
    return df.rename(columns=rename)


def load_ppb(uploaded_file):
    """Baca workbook PPB → (df, error, debug_info).

    df berisi satu baris per item PPB, sudah dibersihkan: kolom nomor jadi angka,
    tanggal jadi datetime, baris tanpa 'No PPB' dibuang. debug_info selalu dict.
    """
    debug_info = {"all_sheets": None, "sheet": None, "header_row": None, "columns": None}

    try:
        sheet_name, all_sheets = select_ppb_sheet(uploaded_file)
        debug_info["all_sheets"] = all_sheets
        debug_info["sheet"] = sheet_name
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membuka file Excel PPB: {exc}", debug_info

    try:
        header_row = detect_ppb_header_row(uploaded_file, sheet_name)
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca file Excel PPB: {exc}", debug_info

    if header_row is None:
        return None, (
            f"Gak nemu baris header di sheet '{sheet_name}' — sudah dicek {MAX_HEADER_SCAN_ROWS} "
            f"baris pertama tapi gak ada kolom 'No PPB'."
        ), debug_info
    debug_info["header_row"] = header_row + 1  # 1-indexed spt Excel

    try:
        uploaded_file.seek(0)
        raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=header_row, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca file Excel PPB: {exc}", debug_info

    # buang kolom "Unnamed" kosong yang muncul dari kolom A yang blank
    raw = raw.loc[:, ~raw.columns.astype(str).str.match(r"Unnamed:.*")]
    df = normalize_ppb_columns(raw)
    debug_info["columns"] = df.columns.tolist()

    missing = [c for c in REQUIRED_PPB_COLUMNS if c not in df.columns]
    if missing:
        cols = ", ".join(f"`{c}`" for c in missing)
        detected = ", ".join(f"`{c}`" for c in df.columns)
        return None, (
            f"Kolom wajib gak ketemu di sheet PPB: {cols}.\n\n"
            f"Sheet dibaca: '{sheet_name}', header di baris ke-{header_row + 1}, "
            f"kolom kebaca: {detected}."
        ), debug_info

    # Baris valid = No PPB DAN Deskripsi Barang sama-sama terisi. Kolom rollup
    # (cntRI/sumRI/cntAmend/cntClose) di sheet asli memakai array-formula yang
    # menutupi seluruh range sheet, jadi ribuan baris kosong tetap "punya" nilai
    # di kolom itu — No PPB + Deskripsi Barang yang membedakan baris item asli.
    df = df[df["No PPB"].notna() & df["Deskripsi Barang"].notna()].copy()
    df["No PPB"] = df["No PPB"].astype(str).str.strip()
    df["Deskripsi Barang"] = df["Deskripsi Barang"].astype(str).str.strip()
    df = df[df["No PPB"].ne("") & df["Deskripsi Barang"].ne("")].copy()

    for col in PPB_NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(_to_number)
    for col in PPB_DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            # sel kosong yang keburu jadi angka ~0 → tanggal 1899/1970; buang
            df.loc[df[col] < pd.Timestamp("2000-01-01"), col] = pd.NaT

    text_cols = [c for c in ["Deskripsi Barang", "Satuan", "Peminta", "Divisi", "Status", "Keterangan"]
                 if c in df.columns]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace("nan", "")

    # urutkan kolom: display dulu, lalu helper, lalu sisanya
    ordered = ([c for c in PPB_DISPLAY_COLUMNS if c in df.columns]
               + [c for c in PPB_HELPER_COLUMNS if c in df.columns]
               + [c for c in df.columns if c not in PPB_DISPLAY_COLUMNS + PPB_HELPER_COLUMNS])
    df = df[ordered].reset_index(drop=True)

    return df, None, debug_info


def ppb_summary(df: pd.DataFrame) -> dict:
    """Ringkasan cepat untuk KPI cards."""
    if df is None or df.empty:
        return {"total_ppb": 0, "total_item": 0, "total_qty": 0.0,
                "per_status": {}, "per_divisi": {}, "date_min": None, "date_max": None}
    return {
        "total_ppb": df["No PPB"].nunique(),
        "total_item": len(df),
        "total_qty": float(df["Kuantitas"].sum()) if "Kuantitas" in df.columns else 0.0,
        "per_status": (df["Status"].replace("", "(kosong)").value_counts().to_dict()
                       if "Status" in df.columns else {}),
        "per_divisi": (df["Divisi"].replace("", "(kosong)").value_counts().head(15).to_dict()
                       if "Divisi" in df.columns else {}),
        "date_min": df["Tgl PPB"].min() if "Tgl PPB" in df.columns else None,
        "date_max": df["Tgl PPB"].max() if "Tgl PPB" in df.columns else None,
    }
