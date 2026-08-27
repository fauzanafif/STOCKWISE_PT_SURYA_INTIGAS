"""Simple rule-based procurement recommendations."""
import pandas as pd

REC_AMAN = "Stok aman, tidak perlu replenishment segera."
REC_REPLENISH = "Segera lakukan replenishment."
REC_PRIORITAS_TINGGI = "Prioritas tinggi untuk procurement."
REC_BEP = "Stok dan Safety Stock sama-sama 0 (BEP) — cek apakah barang ini memang non-aktif atau datanya belum diisi."


def compute_recommendation(df: pd.DataFrame, lead_time_threshold: int) -> pd.Series:
    """Assign a recommendation per row based on Selisih, Lead Time, and the BEP
    condition (Sisa Stok dan Safety Stock sama-sama 0), mirroring how
    utils.calculations.compute_status decides BEP.
    """

    def rec(row):
        if row["Selisih"] >= 0:
            if row["Sisa Stok"] == 0 and row["Safety Stock"] == 0:
                return REC_BEP
            return REC_AMAN
        if row["Lead Time"] >= lead_time_threshold:
            return REC_PRIORITAS_TINGGI
        return REC_REPLENISH

    return df.apply(rec, axis=1)
