"""Baca workbook NPBG (mis. `2. NPBG.xlsx`), sheet **NPBG**.

NPBG = Nota Pengeluaran Barang Gudang — barang yang **keluar** dari gudang.
Sama gaya dengan `utils/ppb_handler.py`: kembalikan `(df, error, debug_info)`,
deteksi sheet & baris header sendiri, tidak menebak struktur.

Struktur sheet NPBG (dari audit file asli):
  kolom A kosong · header di baris ke-3 · kolom:
  No | Tgl NPBG | No NPBG | Tipe NPBG | Klasifikasi | Pelanggan | Nama Proyek |
  No Seri / Nopol | Deskripsi Barang | Kuantitas | Satuan | Peminta |
  Dikeluarkan Oleh | Divisi | Keterangan | Kolom1
Satu No NPBG bisa punya banyak baris (satu baris per item keluar).
"""
from __future__ import annotations

import re

import pandas as pd

NPBG_DISPLAY_COLUMNS = [
    "Tgl NPBG", "No NPBG", "Tipe NPBG", "Klasifikasi", "Deskripsi Barang",
    "Kuantitas", "Satuan", "Peminta", "Divisi", "Pelanggan", "Nama Proyek",
    "No Seri / Nopol", "Dikeluarkan Oleh", "Keterangan",
]
NPBG_HELPER_COLUMNS = ["No", "Kolom1"]

REQUIRED_NPBG_COLUMNS = ["No NPBG", "Deskripsi Barang"]
NPBG_NUMERIC_COLUMNS = ["Kuantitas"]
NPBG_DATE_COLUMNS = ["Tgl NPBG"]

MAX_HEADER_SCAN_ROWS = 15

_CANON = {
    "No NPBG": ["no npbg", "nomor npbg", "no. npbg"],
    "Tgl NPBG": ["tgl npbg", "tanggal npbg", "tgl. npbg"],
    "Tipe NPBG": ["tipe npbg", "jenis npbg", "tipe"],
    "Klasifikasi": ["klasifikasi", "kategori npbg"],
    "Pelanggan": ["pelanggan", "customer"],
    "Nama Proyek": ["nama proyek", "proyek", "project"],
    "No Seri / Nopol": ["no seri / nopol", "no seri/nopol", "no seri", "nopol", "no. seri / nopol"],
    "Deskripsi Barang": ["deskripsi barang", "deskripsi", "nama barang"],
    "Kuantitas": ["kuantitas", "qty", "kuantiti", "jumlah"],
    "Satuan": ["satuan", "uom"],
    "Peminta": ["peminta"],
    "Dikeluarkan Oleh": ["dikeluarkan oleh", "dikeluarkan", "petugas"],
    "Divisi": ["divisi", "departemen", "bagian"],
    "Keterangan": ["keterangan", "catatan"],
    "No": ["no", "no."],
    "Kolom1": ["kolom1", "column1"],
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


def select_npbg_sheet(uploaded_file):
    """Pilih sheet NPBG: persis 'NPBG', lalu yang mengandung 'npbg' (bukan
    'export' / 'dropdown list' / 'klasifikasi'), lalu sheet pertama."""
    uploaded_file.seek(0)
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = xls.sheet_names

    for name in sheets:
        if _norm(name) == "npbg":
            return name, sheets
    for name in sheets:
        n = _norm(name)
        if "npbg" in n and "export" not in n and "klasifikasi" not in n and n != "dropdown list":
            return name, sheets
    return sheets[0], sheets


def detect_npbg_header_row(uploaded_file, sheet_name, max_scan_rows: int = MAX_HEADER_SCAN_ROWS):
    """Cari baris (0-based) yang memuat sel 'No NPBG'."""
    uploaded_file.seek(0)
    preview = pd.read_excel(
        uploaded_file, sheet_name=sheet_name, header=None, nrows=max_scan_rows, engine="openpyxl"
    )
    for idx in range(len(preview)):
        row_values = [_norm(v) for v in preview.iloc[idx].tolist()]
        if any(("no npbg" in v or "nomor npbg" in v) for v in row_values):
            return idx
    return None


def normalize_npbg_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {}
    for canon, variants in _CANON.items():
        for v in variants:
            lookup[v] = canon
    rename = {}
    for col in df.columns:
        key = _norm(col)
        if key in lookup and lookup[key] not in rename.values():
            rename[col] = lookup[key]
    return df.rename(columns=rename)


def load_npbg(uploaded_file):
    """Baca workbook NPBG → (df, error, debug_info).

    df berisi satu baris per item keluar, sudah dibersihkan. debug_info selalu dict.
    """
    debug_info = {"all_sheets": None, "sheet": None, "header_row": None, "columns": None}

    try:
        sheet_name, all_sheets = select_npbg_sheet(uploaded_file)
        debug_info["all_sheets"] = all_sheets
        debug_info["sheet"] = sheet_name
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membuka file Excel NPBG: {exc}", debug_info

    try:
        header_row = detect_npbg_header_row(uploaded_file, sheet_name)
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca file Excel NPBG: {exc}", debug_info

    if header_row is None:
        return None, (
            f"Gak nemu baris header di sheet '{sheet_name}' — sudah dicek {MAX_HEADER_SCAN_ROWS} "
            f"baris pertama tapi gak ada kolom 'No NPBG'."
        ), debug_info
    debug_info["header_row"] = header_row + 1

    try:
        uploaded_file.seek(0)
        raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=header_row, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca file Excel NPBG: {exc}", debug_info

    raw = raw.loc[:, ~raw.columns.astype(str).str.match(r"Unnamed:.*")]
    df = normalize_npbg_columns(raw)
    debug_info["columns"] = df.columns.tolist()

    missing = [c for c in REQUIRED_NPBG_COLUMNS if c not in df.columns]
    if missing:
        cols = ", ".join(f"`{c}`" for c in missing)
        detected = ", ".join(f"`{c}`" for c in df.columns)
        return None, (
            f"Kolom wajib gak ketemu di sheet NPBG: {cols}.\n\n"
            f"Sheet dibaca: '{sheet_name}', header di baris ke-{header_row + 1}, "
            f"kolom kebaca: {detected}."
        ), debug_info

    # Baris valid = No NPBG DAN Deskripsi Barang sama-sama terisi. Sheet asli
    # deklarasi rangenya sangat besar (puluhan ribu baris kosong) — dua kolom
    # ini yang membedakan baris item asli dari padding.
    df = df[df["No NPBG"].notna() & df["Deskripsi Barang"].notna()].copy()
    df["No NPBG"] = df["No NPBG"].astype(str).str.strip()
    df["Deskripsi Barang"] = df["Deskripsi Barang"].astype(str).str.strip()
    df = df[df["No NPBG"].ne("") & df["Deskripsi Barang"].ne("")].copy()

    for col in NPBG_NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(_to_number)
    for col in NPBG_DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df.loc[df[col] < pd.Timestamp("2000-01-01"), col] = pd.NaT

    text_cols = [c for c in ["Deskripsi Barang", "Tipe NPBG", "Klasifikasi", "Pelanggan",
                             "Nama Proyek", "No Seri / Nopol", "Satuan", "Peminta",
                             "Dikeluarkan Oleh", "Divisi", "Keterangan"] if c in df.columns]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace("nan", "")

    ordered = ([c for c in NPBG_DISPLAY_COLUMNS if c in df.columns]
               + [c for c in NPBG_HELPER_COLUMNS if c in df.columns]
               + [c for c in df.columns if c not in NPBG_DISPLAY_COLUMNS + NPBG_HELPER_COLUMNS])
    df = df[ordered].reset_index(drop=True)

    return df, None, debug_info


def npbg_summary(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"total_npbg": 0, "total_item": 0, "total_qty": 0.0,
                "per_klasifikasi": {}, "per_divisi": {}, "per_tipe": {},
                "per_month": {}, "date_min": None, "date_max": None}
    per_month = {}
    if "Tgl NPBG" in df.columns and df["Tgl NPBG"].notna().any():
        m = (df.dropna(subset=["Tgl NPBG"])
               .groupby(df["Tgl NPBG"].dt.strftime("%Y-%m"))["Kuantitas"].sum())
        per_month = m.to_dict()
    return {
        "total_npbg": df["No NPBG"].nunique(),
        "total_item": len(df),
        "total_qty": float(df["Kuantitas"].sum()) if "Kuantitas" in df.columns else 0.0,
        "per_klasifikasi": (df["Klasifikasi"].replace("", "(kosong)").value_counts().head(15).to_dict()
                            if "Klasifikasi" in df.columns else {}),
        "per_divisi": (df["Divisi"].replace("", "(kosong)").value_counts().head(15).to_dict()
                       if "Divisi" in df.columns else {}),
        "per_tipe": (df["Tipe NPBG"].replace("", "(kosong)").value_counts().to_dict()
                     if "Tipe NPBG" in df.columns else {}),
        "per_month": per_month,
        "date_min": df["Tgl NPBG"].min() if "Tgl NPBG" in df.columns else None,
        "date_max": df["Tgl NPBG"].max() if "Tgl NPBG" in df.columns else None,
    }
