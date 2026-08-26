"""Simple rule-based procurement recommendations."""
import pandas as pd

REC_AMAN = "Stok aman, tidak perlu replenishment segera."
REC_REPLENISH = "Segera lakukan replenishment."
REC_PRIORITAS_TINGGI = "Prioritas tinggi untuk procurement."


def compute_recommendation(df: pd.DataFrame, lead_time_threshold: int) -> pd.Series:
    """Assign a recommendation per row based on Selisih and Lead Time."""

    def rec(row):
        if row["Selisih"] >= 0:
            return REC_AMAN
        if row["Lead Time"] >= lead_time_threshold:
            return REC_PRIORITAS_TINGGI
        return REC_REPLENISH

    return df.apply(rec, axis=1)
