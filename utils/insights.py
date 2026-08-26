"""Generate plain-language inventory insights from the active (filtered) dataset."""
import pandas as pd

from utils.calculations import STATUS_TIDAK_AMAN


def generate_insights(df: pd.DataFrame, lead_time_threshold: int) -> list:
    """Return a list of (severity, message) tuples. severity in {success, warning, error}."""
    insights = []

    if df.empty:
        insights.append(("info", "ℹ️ Tidak ada data pada filter yang aktif saat ini."))
        return insights

    unsafe = df[df["Status"] == STATUS_TIDAK_AMAN]

    if unsafe.empty:
        insights.append(("success", "✅ Seluruh inventory berada pada atau di atas safety stock."))
        return insights

    insights.append(("warning", f"⚠️ Terdapat {len(unsafe)} barang yang berada di bawah safety stock."))

    worst = unsafe.loc[unsafe["Defisit"].idxmax()]
    nama = worst.get("Deskripsi Barang") or worst.get("Kode Barang", "-")
    uom = worst.get("UoM", "") or ""
    insights.append((
        "error",
        f"🔴 Defisit stok terbesar terdapat pada {nama} dengan kekurangan {int(worst['Defisit'])} {uom}.".strip(),
    ))

    high_lead_unsafe = unsafe[unsafe["Lead Time"] >= lead_time_threshold]
    if not high_lead_unsafe.empty:
        insights.append((
            "warning",
            f"🟠 Terdapat {len(high_lead_unsafe)} barang dengan kondisi stok di bawah safety stock dan "
            "lead time tinggi. Barang tersebut sebaiknya diprioritaskan untuk procurement.",
        ))

    return insights
