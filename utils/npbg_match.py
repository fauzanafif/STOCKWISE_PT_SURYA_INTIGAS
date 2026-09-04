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

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from utils.calculations import STATUS_AMAN

NPBG_COLUMN = "NPBG"

AUTO_MATCH = 0.90
REVIEW_MATCH = 0.80

# satuan yang sering ditulis nyambung / terpisah dari angkanya
_UNIT_GLUE = re.compile(
    r"(\d)\s+(m3|m2|mm|cm|km|kg|gr|ltr|lt|ml|cc|inch|in|ft|pcs|pc|set|kva|kwh|kw|"
    r"hp|pk|volt|watt|amp|rpm|mah|ah|ph|bar|psi|m|l|v|w|a)\b"
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_X_BETWEEN_NUMS = re.compile(r"(?<=\d)\s*x\s*(?=\d)")


def normalize_text(value) -> str:
    """Turunkan deskripsi ke bentuk kanonik untuk dibandingkan."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")  # buang aksen
    text = text.lower()
    text = text.replace("³", "3").replace("²", "2")
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)   # 1,5 -> 1.5
    text = _NON_ALNUM.sub(" ", text)              # tanda baca -> spasi
    text = re.sub(r"\s+", " ", text).strip()
    text = _UNIT_GLUE.sub(r"\1\2", text)          # "6 m3" -> "6m3"
    text = _X_BETWEEN_NUMS.sub("x", text)         # "10 x 100" -> "10x100"
    return text


def spec_key(norm: str) -> tuple:
    """Kumpulan angka (terurut) di dalam nama — penjaga kapasitas/ukuran.
    Dua deskripsi dengan angka berbeda tidak pernah dianggap barang yang sama."""
    return tuple(sorted(_NUMBER.findall(norm)))


def _token_sorted(norm: str) -> str:
    return " ".join(sorted(norm.split()))


def similarity(a: str, b: str) -> float:
    """Rasio kemiripan 0..1, tahan terhadap urutan kata yang sedikit berbeda."""
    if not a or not b:
        return 0.0
    direct = SequenceMatcher(None, a, b).ratio()
    if direct >= AUTO_MATCH or direct < 0.6:
        return direct
    reordered = SequenceMatcher(None, _token_sorted(a), _token_sorted(b)).ratio()
    return max(direct, reordered)


def match_verdict(sim: float) -> str:
    if sim >= AUTO_MATCH:
        return "MATCH"
    if sim >= REVIEW_MATCH:
        return "REVIEW"
    return "NO_MATCH"


def _is_match(a_norm: str, a_tokens: frozenset, b_norm: str, sm: SequenceMatcher) -> bool:
    """Versi cepat dari `match_verdict(similarity(...)) == "MATCH"` untuk loop
    besar. Gate murah dulu (harus berbagi minimal satu kata utuh; panjang tidak
    terlalu jauh), baru SequenceMatcher.
    """
    b_tokens = frozenset(b_norm.split())
    if a_tokens and b_tokens and not (a_tokens & b_tokens):
        return False
    la, lb = len(a_norm), len(b_norm)
    if abs(la - lb) > 0.35 * max(la, lb, 1):
        return False
    sm.set_seq1(b_norm)
    if sm.real_quick_ratio() < AUTO_MATCH:
        return False
    quick = sm.quick_ratio()
    if quick < AUTO_MATCH:
        # ratio() can't reach AUTO_MATCH either (quick_ratio is an upper bound);
        # only a word-order-different variant could still match.
        if quick < 0.6:
            return False
        return SequenceMatcher(None, _token_sorted(a_norm), _token_sorted(b_norm)).ratio() >= AUTO_MATCH
    return sm.ratio() >= AUTO_MATCH


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
        if cand_norm == norm or _is_match(norm, tokens, cand_norm, sm):
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
