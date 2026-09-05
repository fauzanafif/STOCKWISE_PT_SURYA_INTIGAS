"""Primitif normalisasi teks + fuzzy matching deskripsi barang — dipakai
bersama oleh `utils/npbg_match.py` dan `utils/ppb_ri_match.py` supaya aturan
"typo 1-2 huruf MATCH, tapi kapasitas/ukuran beda NO MATCH" konsisten di
seluruh aplikasi (satu tempat, tidak diduplikasi per fitur).

Ambang similarity:
    >= 0.90  -> MATCH (dipakai)
    0.80-0.89 -> REVIEW (mirip, tapi tidak dianggap match otomatis)
    < 0.80   -> NO MATCH
Similarity bukan satu-satunya penentu: `spec_key` (kumpulan angka pada nama)
harus identik dulu sebelum similarity diperiksa — jadi "OXYGEN GAS 6M3" tidak
akan pernah cocok dengan "OXYGEN GAS 10M3" walau teksnya sangat mirip.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

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
    """Kumpulan angka (terurut) di dalam nama — penjaga kapasitas/ukuran/model.
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


# Kata pendek (typo/singkatan wajar) masih dianggap kata yang sama kalau rasio
# kemiripannya di atas ambang ini; di bawahnya dianggap kata yang BEDA
# (atribut/spesifikasi berbeda), berapa pun similarity string keseluruhannya.
# Dikalibrasi dari kasus nyata: "gas"/"gaz" (typo 1 huruf) = 0.667,
# "oxygen"/"oksigen" (singkatan/ejaan) = 0.615 — harus tetap MATCH.
# "seamless"/"welded" (jenis sambungan beda) = 0.429, "hitam"/"putih" = 0.2 —
# harus NO MATCH walau sisa kalimatnya identik.
TOKEN_ALIGN_THRESHOLD = 0.5


def _best_token_ratio(token: str, others: list) -> float:
    if token in others:
        return 1.0
    if not others:
        return 0.0
    return max(SequenceMatcher(None, token, o).ratio() for o in others)


def tokens_align(a_norm: str, b_norm: str) -> bool:
    """False kalau ada satu kata pun (di kedua sisi) yang tidak punya padanan
    cukup mirip di sisi lain — sinyal satu atribut/spesifikasi (tipe sambungan,
    material, warna, dst.) benar-benar berbeda, bukan sekadar typo/singkatan.
    Ini yang mencegah "FITTING ... SCH 40 SEAMLESS" dianggap sama dengan
    "FITTING ... SCH 40 WELDED" — similarity string keseluruhannya tinggi
    (kata lain semua identik) tapi kata pembedanya sama sekali beda.
    """
    a_tok, b_tok = a_norm.split(), b_norm.split()
    return (
        all(_best_token_ratio(t, b_tok) >= TOKEN_ALIGN_THRESHOLD for t in a_tok)
        and all(_best_token_ratio(t, a_tok) >= TOKEN_ALIGN_THRESHOLD for t in b_tok)
    )


def is_match(a_norm: str, a_tokens: frozenset, b_norm: str, sm: SequenceMatcher) -> bool:
    """Versi cepat dari `classify(a_norm, b_norm) == "MATCH"` untuk loop besar.
    Gate murah dulu (harus berbagi minimal satu kata utuh; panjang tidak
    terlalu jauh; lalu SequenceMatcher), baru `tokens_align` sebagai veto
    terakhir sebelum menyatakan MATCH. `sm` sebaiknya sudah di-`set_seq2`
    dengan `a_norm` oleh pemanggil supaya cache internal `SequenceMatcher`
    (`set_seq2`) dipakai ulang di semua kandidat `b_norm`.
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
        return (
            SequenceMatcher(None, _token_sorted(a_norm), _token_sorted(b_norm)).ratio() >= AUTO_MATCH
            and tokens_align(a_norm, b_norm)
        )
    return sm.ratio() >= AUTO_MATCH and tokens_align(a_norm, b_norm)


def classify(a_norm: str, b_norm: str) -> str:
    """Verdict lengkap (MATCH/REVIEW/NO_MATCH) untuk sepasang teks yang SUDAH
    dinormalisasi, termasuk veto `tokens_align` — dipakai untuk pemakaian
    sederhana/skrip uji. Loop besar pakai `is_match` (dioptimasi dengan
    SequenceMatcher yang dipakai ulang); hasil akhir keduanya konsisten."""
    verdict = match_verdict(similarity(a_norm, b_norm))
    if verdict == "MATCH" and not tokens_align(a_norm, b_norm):
        return "REVIEW"
    return verdict
