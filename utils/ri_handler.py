"""Baca sheet **RI** (Receive Item) di dalam workbook PPB (mis. `1. PPB - RI.xlsx`).

RI = bukti barang yang benar-benar **diterima** dari vendor, biasanya (tapi
tidak selalu — lihat catatan di bawah) terkait ke satu No PPB.

Sama gaya dengan `utils/ppb_handler.py` / `utils/npbg_handler.py`: kembalikan
`(df, error, debug_info)`, deteksi sheet & baris header sendiri, tidak pernah
menebak struktur.

Struktur sheet RI (dari audit file asli `1. PPB - RI.xlsx`):
  judul "Receive Item (RI)" di baris 1 · header di baris ke-5 · kolom:
  No | Tgl RI | No RI | Deskripsi Barang | Kuantitas | Satuan | No PPB | No PO |
  Vendor | No Surat Jalan | Pemeriksa | Keterangan
Beda dari PPB/NPBG: sheet RI TIDAK punya padding baris kosong (semua baris
"No RI" & "Deskripsi Barang" terisi) — tapi ~55% barisnya `No PPB` KOSONG
(diterima tanpa tercatat nomor PPB-nya). `utils/ppb_ri_match.py` yang
menangani konsekuensi ini saat mencocokkan RI ke Inventory/PPB.

RI **opsional**: kalau sheet "RI" tidak ada di workbook yang diupload untuk
PPB, itu bukan error — banyak workbook PPB polos tidak menyertakannya. Fitur
lain yang bergantung pada PPB tetap jalan tanpa RI.
"""
from __future__ import annotations

import re

import pandas as pd

RI_DISPLAY_COLUMNS = [
    "Tgl RI", "No RI", "Deskripsi Barang", "Kuantitas", "Satuan",
    "No PPB", "No PO", "Vendor", "No Surat Jalan", "Pemeriksa", "Keterangan",
]
RI_HELPER_COLUMNS = ["No"]

REQUIRED_RI_COLUMNS = ["No RI", "Deskripsi Barang"]
RI_NUMERIC_COLUMNS = ["Kuantitas"]
RI_DATE_COLUMNS = ["Tgl RI"]

MAX_HEADER_SCAN_ROWS = 15

_CANON = {
    "No RI": ["no ri", "nomor ri", "no. ri"],
    "Tgl RI": ["tgl ri", "tanggal ri", "tgl. ri"],
    "Deskripsi Barang": ["deskripsi barang", "deskripsi", "nama barang"],
    "Kuantitas": ["kuantitas", "qty", "kuantiti", "jumlah"],
    "Satuan": ["satuan", "uom"],
    "No PPB": ["no ppb", "nomor ppb", "no. ppb"],
    "No PO": ["no po", "nomor po", "no. po"],
    "Vendor": ["vendor", "supplier"],
    "No Surat Jalan": ["no surat jalan", "no. surat jalan", "surat jalan"],
    "Pemeriksa": ["pemeriksa"],
    "Keterangan": ["keterangan", "catatan"],
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


def select_ri_sheet(uploaded_file):
    """Cari sheet bernama persis 'RI'. Return (nama, semua_sheet) — nama jadi
    None kalau tidak ada (RI opsional, bukan error)."""
    uploaded_file.seek(0)
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
    sheets = xls.sheet_names
    for name in sheets:
        if _norm(name) == "ri":
            return name, sheets
    return None, sheets


def detect_ri_header_row(uploaded_file, sheet_name, max_scan_rows: int = MAX_HEADER_SCAN_ROWS):
    """Cari baris (0-based) yang memuat sel 'No RI'."""
    uploaded_file.seek(0)
    preview = pd.read_excel(
        uploaded_file, sheet_name=sheet_name, header=None, nrows=max_scan_rows, engine="openpyxl"
    )
    for idx in range(len(preview)):
        row_values = [_norm(v) for v in preview.iloc[idx].tolist()]
        if any(("no ri" in v or "nomor ri" in v) for v in row_values):
            return idx
    return None


def normalize_ri_columns(df: pd.DataFrame) -> pd.DataFrame:
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


def load_ri(uploaded_file):
    """Baca sheet RI dari workbook PPB yang sama → (df, error, debug_info).

    Beda dari load_ppb/load_npbg: kalau sheet "RI" memang tidak ada di
    workbook, itu bukan error — `(None, None, debug_info)` dikembalikan supaya
    pemanggil tahu "tidak ada data RI" tanpa menampilkan pesan error ke user.
    Error string hanya dipakai kalau sheet RI ADA tapi strukturnya rusak.
    """
    debug_info = {"all_sheets": None, "sheet": None, "header_row": None, "columns": None}

    try:
        sheet_name, all_sheets = select_ri_sheet(uploaded_file)
        debug_info["all_sheets"] = all_sheets
        debug_info["sheet"] = sheet_name
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membuka file Excel untuk sheet RI: {exc}", debug_info

    if sheet_name is None:
        return None, None, debug_info  # tidak ada sheet RI — bukan error

    try:
        header_row = detect_ri_header_row(uploaded_file, sheet_name)
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca sheet RI: {exc}", debug_info

    if header_row is None:
        return None, (
            f"Sheet 'RI' ditemukan tapi baris header ('No RI') tidak ketemu di "
            f"{MAX_HEADER_SCAN_ROWS} baris pertama."
        ), debug_info
    debug_info["header_row"] = header_row + 1  # 1-indexed spt Excel

    try:
        uploaded_file.seek(0)
        raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=header_row, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001
        return None, f"Gagal membaca sheet RI: {exc}", debug_info

    raw = raw.loc[:, ~raw.columns.astype(str).str.match(r"Unnamed:.*")]
    df = normalize_ri_columns(raw)
    debug_info["columns"] = df.columns.tolist()

    missing = [c for c in REQUIRED_RI_COLUMNS if c not in df.columns]
    if missing:
        cols = ", ".join(f"`{c}`" for c in missing)
        detected = ", ".join(f"`{c}`" for c in df.columns)
        return None, (
            f"Kolom wajib gak ketemu di sheet RI: {cols}.\n\n"
            f"Header di baris ke-{header_row + 1}, kolom kebaca: {detected}."
        ), debug_info

    df = df[df["No RI"].notna() & df["Deskripsi Barang"].notna()].copy()
    df["No RI"] = df["No RI"].astype(str).str.strip()
    df["Deskripsi Barang"] = df["Deskripsi Barang"].astype(str).str.strip()
    df = df[df["No RI"].ne("") & df["Deskripsi Barang"].ne("")].copy()

    for col in RI_NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(_to_number)
    for col in RI_DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df.loc[df[col] < pd.Timestamp("2000-01-01"), col] = pd.NaT

    text_cols = [c for c in ["Deskripsi Barang", "Satuan", "No PPB", "No PO", "Vendor",
                             "No Surat Jalan", "Pemeriksa", "Keterangan"] if c in df.columns]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace("nan", "")

    ordered = ([c for c in RI_DISPLAY_COLUMNS if c in df.columns]
               + [c for c in RI_HELPER_COLUMNS if c in df.columns]
               + [c for c in df.columns if c not in RI_DISPLAY_COLUMNS + RI_HELPER_COLUMNS])
    df = df[ordered].reset_index(drop=True)

    return df, None, debug_info
