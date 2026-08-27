"""Generate plain-language inventory insights from the active (filtered) dataset."""
import pandas as pd

from utils.calculations import STATUS_BEP, STATUS_TIDAK_AMAN


def generate_insights(df: pd.DataFrame, lead_time_threshold: int) -> list:
    """Return a list of (severity, message) tuples. severity in {success, warning, error}."""
    insights = []

    if df.empty:
        insights.append(("info", "ℹ️ Belum ada data yang cocok dengan filter ini."))
        return insights

    bep = df[df["Status"] == STATUS_BEP]
    if not bep.empty:
        insights.append((
            "info",
            f"🎯 Ada {len(bep)} barang berstatus BEP (Sisa Stok & Safety Stock sama-sama 0) — "
            "cek apakah barang ini memang non-aktif atau datanya belum diisi.",
        ))

    unsafe = df[df["Status"] == STATUS_TIDAK_AMAN]

    if unsafe.empty:
        insights.append(("success", "✅ Semua stok lainnya aman, masih di atas safety stock."))
        return insights

    insights.append(("warning", f"⚠️ Ada {len(unsafe)} barang yang stoknya di bawah safety stock."))

    worst = unsafe.loc[unsafe["Defisit"].idxmax()]
    nama = worst.get("Deskripsi Barang") or worst.get("Kode Barang", "-")
    uom = worst.get("UoM", "") or ""
    insights.append((
        "error",
        f"🔴 Defisit paling besar ada di {nama}, kurang {int(worst['Defisit'])} {uom}.".strip(),
    ))

    high_lead_unsafe = unsafe[unsafe["Lead Time"] >= lead_time_threshold]
    if not high_lead_unsafe.empty:
        insights.append((
            "warning",
            f"🟠 {len(high_lead_unsafe)} barang stoknya kurang dan lead time-nya lama — ini yang "
            "paling perlu diprioritaskan buat dibeli.",
        ))

    return insights
