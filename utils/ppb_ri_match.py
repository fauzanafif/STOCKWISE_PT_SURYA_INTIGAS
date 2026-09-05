"""Cocokkan barang Inventory dengan baris PPB & RI lewat `Deskripsi Barang`,
lalu turunkan Status Pengadaan per barang.

Prinsip:
- SEMUA barang Inventory diproses — AMAN, TIDAK AMAN, maupun BEP — bukan cuma
  yang TIDAK AMAN. Barang AMAN pun bisa sedang/baru saja diproses pembelian.
- PPB dicocokkan lewat Deskripsi Barang, fuzzy (primitif dari `utils.text_match`
  — mesin yang sama persis dipakai `utils.npbg_match`, supaya "typo 1-2 huruf
  MATCH, kapasitas beda NO MATCH" konsisten di seluruh aplikasi).
- RI dicocokkan dalam dua lapis:
    1) Fuzzy Deskripsi Barang ke SELURUH baris RI (mesin yang sama).
    2) Di antara kandidat itu, yang `No PPB`-nya sama dengan salah satu PPB
       yang sudah match diprioritaskan (bukti kuat: barang ini memang
       diterima atas permintaan pembelian yang sama). Kalau tidak ada
       kandidat yang No PPB-nya cocok — dan itu situasi umum, ~55% baris RI
       di data nyata kolom No PPB-nya kosong — tetap pakai seluruh kandidat
       hasil fuzzy Deskripsi. No PPB dipakai sebagai *penguat kepercayaan*,
       bukan syarat mutlak, supaya RI yang datanya tidak lengkap tidak
       terlewat begitu saja.
    3) Satuan (kalau tersedia di kedua sisi) jadi saringan lunak terakhir:
       kalau ada kandidat yang satuannya cocok/kosong, pakai itu saja.
- Status Pengadaan diturunkan dari kombinasi ADA/tidaknya PPB & RI + qty.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from utils.text_match import is_match, normalize_text, spec_key

PPB_COLUMNS = ["PPB", "Tgl PPB", "No PPB", "Qty PPB"]
RI_COLUMNS = ["RI", "Tgl RI", "No RI", "Qty RI"]
STATUS_COLUMN = "Status Pengadaan"
NEW_COLUMNS = PPB_COLUMNS + RI_COLUMNS + [STATUS_COLUMN]

STATUS_BELUM_PPB = "BELUM DI-PPB"
STATUS_MENUNGGU_RI = "MENUNGGU RI"
STATUS_SEBAGIAN_DITERIMA = "SEBAGIAN DITERIMA"
STATUS_SUDAH_DITERIMA = "SUDAH DITERIMA"

_EMPTY_ROW = {
    "PPB": None, "Tgl PPB": pd.NaT, "No PPB": None, "Qty PPB": np.nan,
    "RI": None, "Tgl RI": pd.NaT, "No RI": None, "Qty RI": np.nan,
    "Status Pengadaan": STATUS_BELUM_PPB,
}


def _build_index(descriptions):
    """norm per posisi (list, sejajar dengan `descriptions`) +
    {spec_key: {norm: [posisi, ...]}} untuk lookup fuzzy yang cepat."""
    norms = [normalize_text(d) for d in descriptions]
    index: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for pos, norm in enumerate(norms):
        if norm:
            index[spec_key(norm)][norm].append(pos)
    return norms, index


def _matched_positions(norm: str, index: dict) -> list:
    """Posisi semua baris (di dataframe sumber) yang deskripsinya MATCH `norm`."""
    if not norm:
        return []
    candidates = index.get(spec_key(norm), {})
    if not candidates:
        return []
    tokens = frozenset(norm.split())
    sm = SequenceMatcher(None)
    sm.set_seq2(norm)
    positions = []
    for cand_norm, cand_positions in candidates.items():
        if cand_norm == norm or is_match(norm, tokens, cand_norm, sm):
            positions.extend(cand_positions)
    return positions


def _latest_row(rows: pd.DataFrame, date_col: str):
    """Baris "paling relevan/terakhir": tanggal terbesar; kalau tanggalnya
    kosong semua, baris terakhir apa adanya (asumsi file tersusun kronologis,
    sama seperti asumsi PPB/NPBG di tempat lain di app)."""
    if date_col in rows.columns and rows[date_col].notna().any():
        return rows.loc[rows[date_col].idxmax()]
    return rows.iloc[-1]


def _safe(row, col):
    value = row.get(col) if col in row.index else None
    return None if (value is None or (isinstance(value, float) and pd.isna(value))) else value


def build_procurement_status(inv_descriptions, ppb_df: pd.DataFrame | None,
                             ri_df: pd.DataFrame | None) -> dict:
    """{deskripsi_inventory_asli: {kolom_baru: nilai}} untuk SETIAP deskripsi
    unik di `inv_descriptions` — dipanggil untuk seluruh barang Inventory, apa
    pun Status-nya (AMAN/TIDAK AMAN/BEP)."""
    uniques = set(inv_descriptions)

    have_ppb = (
        ppb_df is not None and not ppb_df.empty
        and "Deskripsi Barang" in ppb_df.columns and "No PPB" in ppb_df.columns
    )
    if not have_ppb:
        return {d: dict(_EMPTY_ROW) for d in uniques}

    ppb_df = ppb_df.reset_index(drop=True)
    _, ppb_index = _build_index(ppb_df["Deskripsi Barang"])
    ppb_has_satuan = "Satuan" in ppb_df.columns
    ppb_has_qty = "Kuantitas" in ppb_df.columns
    ppb_has_date = "Tgl PPB" in ppb_df.columns

    have_ri = (
        ri_df is not None and not ri_df.empty
        and "Deskripsi Barang" in ri_df.columns
    )
    ri_index = {}
    if have_ri:
        ri_df = ri_df.reset_index(drop=True)
        _, ri_index = _build_index(ri_df["Deskripsi Barang"])
        ri_has_no_ppb = "No PPB" in ri_df.columns
        ri_has_satuan = "Satuan" in ri_df.columns
        ri_has_qty = "Kuantitas" in ri_df.columns
        ri_has_date = "Tgl RI" in ri_df.columns

    out: dict = {}
    for raw in uniques:
        norm = normalize_text(raw)
        ppb_positions = _matched_positions(norm, ppb_index)
        if not ppb_positions:
            out[raw] = dict(_EMPTY_ROW)
            continue

        ppb_rows = ppb_df.iloc[sorted(set(ppb_positions))]
        no_ppb_set = set(ppb_rows["No PPB"].dropna().astype(str)) - {""}
        qty_ppb = float(ppb_rows["Kuantitas"].sum()) if ppb_has_qty else np.nan
        latest_ppb = _latest_row(ppb_rows, "Tgl PPB") if ppb_has_date else ppb_rows.iloc[-1]
        ref_satuan = str(_safe(latest_ppb, "Satuan") or "").strip().lower() if ppb_has_satuan else ""

        row = dict(_EMPTY_ROW)
        row.update({
            "PPB": "ADA",
            "Tgl PPB": _safe(latest_ppb, "Tgl PPB") if ppb_has_date else pd.NaT,
            "No PPB": _safe(latest_ppb, "No PPB"),
            "Qty PPB": qty_ppb,
        })

        ri_matched = pd.DataFrame()
        if have_ri:
            ri_positions = _matched_positions(norm, ri_index)
            if ri_positions:
                candidates = ri_df.iloc[sorted(set(ri_positions))]
                # No PPB sebagai penguat kepercayaan: pakai subset yang
                # No PPB-nya cocok kalau ADA; kalau tidak ada satupun (umum —
                # ~55% baris RI No PPB-nya kosong), tetap pakai seluruh
                # kandidat hasil fuzzy Deskripsi Barang.
                if ri_has_no_ppb and no_ppb_set:
                    confirmed = candidates[candidates["No PPB"].astype(str).isin(no_ppb_set)]
                    ri_matched = confirmed if not confirmed.empty else candidates
                else:
                    ri_matched = candidates
                # Satuan: saringan lunak terakhir — kalau ada kandidat yang
                # satuannya cocok/kosong, persempit ke situ; kalau tidak ada
                # satupun yang cocok, jangan buang semua bukti — tetap pakai
                # kandidat apa adanya (satuan bisa ditulis beda-beda).
                if ri_has_satuan and ref_satuan and not ri_matched.empty:
                    ri_satuan = ri_matched["Satuan"].astype(str).str.strip().str.lower()
                    same = ri_matched[(ri_satuan == ref_satuan) | (ri_satuan == "")]
                    if not same.empty:
                        ri_matched = same

        if ri_matched.empty:
            row["Status Pengadaan"] = STATUS_MENUNGGU_RI
        else:
            qty_ri = float(ri_matched["Kuantitas"].sum()) if ri_has_qty else np.nan
            latest_ri = _latest_row(ri_matched, "Tgl RI") if ri_has_date else ri_matched.iloc[-1]
            row.update({
                "RI": "ADA",
                "Tgl RI": _safe(latest_ri, "Tgl RI") if ri_has_date else pd.NaT,
                "No RI": _safe(latest_ri, "No RI"),
                "Qty RI": qty_ri,
            })
            if not np.isnan(qty_ri) and not np.isnan(qty_ppb) and qty_ri < qty_ppb:
                row["Status Pengadaan"] = STATUS_SEBAGIAN_DITERIMA
            else:
                row["Status Pengadaan"] = STATUS_SUDAH_DITERIMA
        out[raw] = row

    return out


def attach_procurement_columns(inv_df: pd.DataFrame, ppb_df: pd.DataFrame | None = None,
                               ri_df: pd.DataFrame | None = None,
                               *, status_map: dict | None = None) -> pd.DataFrame:
    """Kembalikan salinan `inv_df` dengan 9 kolom baru (`PPB`, `Tgl PPB`,
    `No PPB`, `Qty PPB`, `RI`, `Tgl RI`, `No RI`, `Qty RI`, `Status Pengadaan`)
    di paling kanan. Dihitung untuk SEMUA baris, apa pun Status Inventory-nya.

    `status_map` (opsional) = hasil `build_procurement_status` yang sudah
    dihitung/di-cache; kalau tidak diberikan, dihitung langsung dari
    `ppb_df`/`ri_df`.
    """
    inv_df = inv_df.drop(columns=NEW_COLUMNS, errors="ignore").copy()

    if "Deskripsi Barang" not in inv_df.columns:
        for col in NEW_COLUMNS:
            inv_df[col] = _EMPTY_ROW.get(col, pd.NA) if col != STATUS_COLUMN else STATUS_BELUM_PPB
        return inv_df

    if status_map is None:
        status_map = build_procurement_status(inv_df["Deskripsi Barang"].unique(), ppb_df, ri_df)

    resolved = inv_df["Deskripsi Barang"].map(lambda d: status_map.get(d, _EMPTY_ROW))
    for col in NEW_COLUMNS:
        values = resolved.map(lambda r: r.get(col))
        if col in ("Qty PPB", "Qty RI"):
            inv_df[col] = pd.to_numeric(pd.Series(values.tolist(), index=inv_df.index), errors="coerce")
        elif col in ("Tgl PPB", "Tgl RI"):
            inv_df[col] = pd.to_datetime(pd.Series(values.tolist(), index=inv_df.index), errors="coerce")
        else:
            inv_df[col] = pd.Series(values.tolist(), index=inv_df.index, dtype="object")

    return inv_df
