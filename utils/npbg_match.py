"""Cocokkan barang Inventory dengan baris NPBG lewat `Deskripsi Barang`, lalu
isi kolom `NPBG` = berapa banyak baris NPBG untuk barang itu.

Pencocokan sengaja toleran terhadap beda kecil pada teks — typo 1-2 huruf,
huruf besar/kecil, spasi, format satuan, singkatan, urutan kata yang sedikit
beda — TAPI tidak toleran terhadap beda spesifikasi: angka kapasitas/ukuran/
model harus sama persis, jadi "OXYGEN GAS 6M3" tidak akan pernah cocok dengan
"OXYGEN GAS 10M3".

Ambang similarity:
    >= 0.90  -> MATCH (dipakai)
    0.80-0.89 -> REVIEW (mirip, tapi tidak dianggap match otomatis)
    < 0.80   -> NO MATCH
Similarity bukan satu-satunya penentu: `spec_key` (kumpulan angka pada nama)
harus identik dulu sebelum similarity diperiksa.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from utils.calculations import STATUS_AMAN
from utils.text_match import AUTO_MATCH, REVIEW_MATCH, is_match, match_verdict, normalize_text, similarity, spec_key

NPBG_COLUMN = "NPBG"

# Re-exported for backward compatibility — the actual implementations moved to
# utils.text_match (shared with utils.ppb_ri_match) so the matching rules live
# in exactly one place.
__all__ = [
    "NPBG_COLUMN", "AUTO_MATCH", "REVIEW_MATCH", "normalize_text", "spec_key", "similarity",
    "match_verdict", "build_npbg_buckets", "count_for", "build_count_map", "attach_npbg_column",
]


def build_npbg_buckets(npbg_descriptions) -> dict:
    """{spec_key: [(deskripsi_ternormalisasi, jumlah_baris), ...]} dari seluruh
    baris `Deskripsi Barang` di file NPBG."""
    norm = pd.Series(list(npbg_descriptions), dtype="object").map(normalize_text)
    counts = norm[norm != ""].value_counts()
    buckets: dict[tuple, list] = defaultdict(list)
    for desc_norm, cnt in counts.items():
        buckets[spec_key(desc_norm)].append((desc_norm, int(cnt)))
    return buckets


def count_for(norm: str, buckets: dict):
    """Total baris NPBG yang cocok dengan satu deskripsi inventory (sudah
    dinormalisasi). Mengembalikan pd.NA kalau tidak ada yang MATCH."""
    if not norm:
        return pd.NA
    candidates = buckets.get(spec_key(norm), ())
    if not candidates:
        return pd.NA
    tokens = frozenset(norm.split())
    sm = SequenceMatcher(None)
    sm.set_seq2(norm)
    total = 0
    matched = False
    for cand_norm, cnt in candidates:
        if cand_norm == norm or is_match(norm, tokens, cand_norm, sm):
            total += cnt
            matched = True
    return total if matched else pd.NA


def build_count_map(inv_descriptions, npbg_descriptions) -> dict:
    """{deskripsi_inventory_asli: jumlah_baris_NPBG_yang_match | None}.

    Dihitung untuk daftar deskripsi (biasanya deskripsi barang AMAN yang unik)
    supaya bisa di-cache terpisah dari DataFrame inventory yang sering berubah.
    """
    buckets = build_npbg_buckets(npbg_descriptions)
    out: dict = {}
    for raw in inv_descriptions:
        value = count_for(normalize_text(raw), buckets)
        out[raw] = None if value is pd.NA else int(value)
    return out


def attach_npbg_column(inv_df: pd.DataFrame, npbg_df: pd.DataFrame | None = None,
                       *, count_map: dict | None = None) -> pd.DataFrame:
    """Kembalikan salinan `inv_df` dengan kolom `NPBG` di paling kanan.

    NPBG hanya diisi untuk barang berstatus AMAN yang deskripsinya cocok dengan
    baris di file NPBG; selain itu NULL (pd.NA — jangan diubah jadi 0).

    `count_map` (opsional) = hasil `build_count_map` yang sudah dihitung/di-cache;
    kalau tidak diberikan, dihitung langsung dari `npbg_df`.
    """
    inv_df = inv_df.drop(columns=[NPBG_COLUMN], errors="ignore").copy()
    # NaN = NULL: "tidak ada pasangan di file NPBG", atau status bukan AMAN.
    # Jangan pernah diisi 0 — 0 dan "tidak ketemu" beda arti.
    result = pd.Series(np.nan, index=inv_df.index, dtype="float64")

    has_cols = "Deskripsi Barang" in inv_df.columns and "Status" in inv_df.columns
    if count_map is None:
        usable = (
            has_cols and npbg_df is not None and not npbg_df.empty
            and "Deskripsi Barang" in npbg_df.columns
        )
        if not usable:
            inv_df[NPBG_COLUMN] = result
            return inv_df
        aman_desc = inv_df.loc[inv_df["Status"] == STATUS_AMAN, "Deskripsi Barang"].unique()
        count_map = build_count_map(aman_desc, npbg_df["Deskripsi Barang"].tolist())

    if has_cols:
        aman = inv_df["Status"] == STATUS_AMAN
        result.loc[aman] = inv_df.loc[aman, "Deskripsi Barang"].map(
            lambda d: count_map.get(d) if count_map.get(d) is not None else np.nan
        )

    inv_df[NPBG_COLUMN] = result
    return inv_df
