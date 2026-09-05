"""Generate plain-language inventory insights from the active (filtered) dataset."""
import pandas as pd

from utils.calculations import STATUS_BEP, STATUS_TIDAK_AMAN


def generate_insights(df: pd.DataFrame, lead_time_threshold: int) -> list:
    """Return a list of (severity, message) tuples. severity in {success, warning, error}.

    Bahasanya sengaja dibuat seawam mungkin — hindari istilah teknis (BEP,
    Defisit, Lead Time, Safety Stock) dan ganti dengan kalimat yang langsung
    kebayang maksudnya, karena ini catatan paling bawah yang dibaca orang yang
    mungkin nggak familiar dengan istilah gudang/procurement sama sekali.
    """
    insights = []

    if df.empty:
        insights.append(("info", "ℹ️ Belum ada data yang cocok dengan filter ini."))
        return insights

    bep = df[df["Status"] == STATUS_BEP]
    if not bep.empty:
        insights.append((
            "info",
            f"🎯 **{len(bep)} barang** belum punya batas stok sama sekali (stok dan batas amannya "
            "sama-sama kosong) — coba cek dulu, barang ini masih aktif dipakai atau datanya "
            "memang belum diisi.",
        ))

    unsafe = df[df["Status"] == STATUS_TIDAK_AMAN]

    if unsafe.empty:
        insights.append(("success", "✅ Sisanya aman — stoknya masih cukup, belum perlu dibeli lagi."))
        return insights

    insights.append((
        "warning",
        f"⚠️ **{len(unsafe)} barang** stoknya sudah di bawah batas aman — sebaiknya mulai dipesan.",
    ))

    worst = unsafe.loc[unsafe["Defisit"].idxmax()]
    nama = worst.get("Deskripsi Barang") or worst.get("Kode Barang", "-")
    uom = worst.get("UoM", "") or ""
    qty = f"{int(worst['Defisit'])} {uom}".strip()
    insights.append((
        "error",
        f"🔴 Yang paling mendesak: **{nama}**, kurang {qty} dari batas amannya.",
    ))

    high_lead_unsafe = unsafe[unsafe["Lead Time"] >= lead_time_threshold]
    if not high_lead_unsafe.empty:
        insights.append((
            "warning",
            f"🟠 **{len(high_lead_unsafe)} barang** di antaranya butuh waktu lama untuk datang "
            "kalau baru dipesan sekarang — ini yang paling perlu didahulukan belinya.",
        ))

    return insights
