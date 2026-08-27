"""Reactive calculation pipeline: Selisih, Status, Defisit, Priority Score/Level."""
import numpy as np
import pandas as pd

from utils.excel_handler import CALCULATED_COLUMNS, NUMERIC_COLUMNS
from utils.recommendations import compute_recommendation

STATUS_AMAN = "AMAN"
STATUS_TIDAK_AMAN = "TIDAK AMAN"
STATUS_BEP = "BEP"

DEFAULT_LEAD_TIME_THRESHOLD = 14


def suggest_lead_time_threshold(df: pd.DataFrame) -> int:
    """Pick a sensible default lead-time threshold from the active dataset."""
    if "Lead Time" not in df.columns or df["Lead Time"].dropna().empty:
        return DEFAULT_LEAD_TIME_THRESHOLD
    q75 = df["Lead Time"].quantile(0.75)
    if pd.isna(q75) or q75 <= 0:
        return DEFAULT_LEAD_TIME_THRESHOLD
    return int(round(q75))


def compute_selisih(df: pd.DataFrame) -> pd.Series:
    return df["Sisa Stok"].fillna(0) - df["Safety Stock"].fillna(0)


def compute_status(df: pd.DataFrame) -> pd.Series:
    """AMAN/TIDAK AMAN follow Selisih, except BEP: Sisa Stok dan Safety Stock
    yang keduanya 0 ("break-even" — belum ada kebijakan stok yang jalan),
    yang menang di atas hasil Selisih >= 0.
    """
    selisih = df["Selisih"]
    status = np.where(selisih >= 0, STATUS_AMAN, STATUS_TIDAK_AMAN)
    is_bep = (df["Sisa Stok"].fillna(0) == 0) & (df["Safety Stock"].fillna(0) == 0)
    return np.where(is_bep, STATUS_BEP, status)


def compute_defisit(df: pd.DataFrame) -> pd.Series:
    return (df["Safety Stock"].fillna(0) - df["Sisa Stok"].fillna(0)).clip(lower=0)


def compute_priority_score(df: pd.DataFrame, lead_time_weight: float = 1.0, deficit_weight: float = 2.0) -> pd.Series:
    unsafe = df["Selisih"] < 0
    score = (df["Defisit"].fillna(0) * deficit_weight) + (df["Lead Time"].fillna(0) * lead_time_weight)
    return np.where(unsafe, score, 0.0)


def compute_priority_level(df: pd.DataFrame, lead_time_threshold: int) -> pd.Series:
    """LOW = stok aman. Untuk yang TIDAK AMAN: HIGH kalau defisitnya lebih besar
    dari defisit tipikal barang tidak aman lain, atau lead time-nya tinggi;
    selain itu MEDIUM.
    """
    levels = pd.Series("LOW", index=df.index, dtype=object)
    mask = df["Status"] == STATUS_TIDAK_AMAN
    if mask.sum() == 0:
        return levels

    levels.loc[mask] = "MEDIUM"
    defisit_median = df.loc[mask, "Defisit"].median()
    high_mask = mask & ((df["Defisit"] >= defisit_median) | (df["Lead Time"] >= lead_time_threshold))
    levels.loc[high_mask] = "HIGH"
    return levels


def recalculate(df: pd.DataFrame, lead_time_threshold: int = DEFAULT_LEAD_TIME_THRESHOLD) -> pd.DataFrame:
    """Run the full reactive pipeline and return a df with all calculated columns refreshed."""
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    text_cols = [c for c in df.columns if c not in NUMERIC_COLUMNS and c not in CALCULATED_COLUMNS]
    df[text_cols] = df[text_cols].fillna("").astype(str).replace("nan", "")

    df["Selisih"] = compute_selisih(df)
    df["Status"] = compute_status(df)
    df["Defisit"] = compute_defisit(df)
    df["Priority Score"] = compute_priority_score(df)
    df["Priority Level"] = compute_priority_level(df, lead_time_threshold)
    df["Rekomendasi"] = compute_recommendation(df, lead_time_threshold)
    return df
